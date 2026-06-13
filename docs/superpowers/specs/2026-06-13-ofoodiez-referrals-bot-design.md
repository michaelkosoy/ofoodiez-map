# Ofoodiez Referrals — WhatsApp Candidate↔Advocate Bot (v1 design spec)

> **Status:** design approved 2026-06-13; pending written-spec review.
> **Supersedes** the candidate-facing model in `docs/whatsapp-referral-bot-plan.md`
> (the "search approved referral links" idea) — see §2.

## 1. Summary

A Twilio WhatsApp bot that connects job **candidates** directly with **employee
advocates** at their target companies. A candidate registers, names a target
company, picks a role, drops the job-posting link, and uploads a résumé (PDF);
the application is auto-emailed (via SendGrid) to the active advocates at that
company. **Employees** register as advocates for companies they can refer into
(which also grows the company list). A **Contact Us** path forwards messages to
the operator. The bot is fully button-driven (WhatsApp quick-reply buttons via
the Twilio Content API).

Usage is modest and reactive. It runs inside the existing single-worker
Gunicorn Flask app on Render, reusing the shared SQLAlchemy `db` and the signed,
idempotent, audited `/wa/webhook` shipped in PR1.

## 2. Relationship to prior work

- **PR1 (merged):** delivered the WhatsApp blueprint skeleton, the signed +
  idempotent + audited inbound `/wa/webhook`, `config.py`, `copy.py`, and a
  sqlite pytest harness (+ `run_wa_local.py`). **All reused.** Only the *reply*
  logic changes (route to a state machine; reply via the REST API instead of
  synchronous TwiML).
- **Original plan** (`docs/whatsapp-referral-bot-plan.md`): a different product —
  users searched *approved referral links* by company and got a link;
  submissions were moderated. **This design replaces** that candidate-facing
  model and its `wa_referral_links` table with a candidate/advocate/application
  model (§5). The §4 SQL of that plan has **not** been run in Supabase yet, so
  there is **no migration** — we revise the DDL before first creation. (If it
  was run, drop `wa_referral_links`.)

## 3. Locked decisions

1. **Interaction:** real tappable **quick-reply buttons** via the Twilio
   **Content API** (not TwiML text). Every menu is ≤3 buttons.
2. **Scope:** v1 includes **all three paths** — Candidate, Employee, Contact Us.
3. **Delivery:** candidate applications are **auto-emailed to matched advocates**
   (résumé attached).
4. **Email provider:** **SendGrid**, from `referrals@ofoodiez.com`
   (domain-authenticated).
5. **Employees can add new companies** (get-or-create on registration).
6. **Advocates go active immediately** (a `status` field allows optional
   moderation later).
7. **Résumés** are stored in a **private Supabase Storage** bucket.
8. **Language:** **English-only** for v1; `copy.py` is structured so Hebrew can
   be added later.

## 4. Architecture & core engine

**Reply model.** `/wa/webhook` (PR1) verifies the signature → claims the
`MessageSid` (idempotency) → records the inbound audit row → hands the message
to the dispatcher → returns an **empty 200**. User-facing replies are sent via
the **Twilio REST Messages API** through the Messaging Service **during request
handling** (one to three calls, each ~sub-second; well within the 15-s timeout),
because TwiML cannot carry buttons. A duplicate `MessageSid` is rejected at the
claim step, so no reply is re-sent. Button taps come back to the webhook as
inbound messages carrying the button **payload** (e.g. `PATH_CANDIDATE`), which
the router uses instead of free-text guessing.

**Three isolated, independently testable units:**

1. **Messaging layer** (`whatsapp_bot/messaging.py`) — the only code that calls
   Twilio outbound. `send_text(to, body)` and
   `send_buttons(to, content_sid, variables)`; logs each send to
   `wa_outbound_messages`.
2. **State machine** (`whatsapp_bot/conversation.py` + flow definitions) — pure
   transition logic: given `(flow, step, input)` it validates, computes the next
   `(flow, step, data)`, and returns the message(s) to send. Unit-testable with
   zero network.
3. **Flow definitions** (`whatsapp_bot/flows/`) — the steps for registration /
   candidate / employee / contact, as data + small handlers.

**Supporting modules:** `storage.py` (Supabase Storage), `emailer.py`
(SendGrid), `matching.py` (company normalize + advocate lookup), `copy.py`
(strings), `config.py` (env), `models.py` (ORM), `webhooks.py` (inbound entry,
reused from PR1 with new dispatch).

Conversation state lives in the DB (`wa_conversations`) so it survives restarts
and works across gthreads. Each inbound: load state → dispatch → persist new
state → send next message(s).

## 5. Data model

All tables are `wa_`-prefixed, on the shared `db`. **RLS enabled (no policies)**
— the app connects as the table owner and bypasses non-forced RLS (per PR1).
Created via the revised `whatsapp_bot/schema.sql`, run once in Supabase. Primary
keys are bigint identity (sqlite `Integer` variant for tests, per PR1).

### Identity & conversation

**`wa_users`** — one row per WhatsApp contact.
`id`, `phone` (unique, E.164), `profile_name`, `first_name`, `last_name`,
`email`, `terms_accepted_at`, `last_language` (default `en`), `is_blocked`,
`created_at`, `updated_at`. One person can be both candidate and advocate.

**`wa_conversations`** — live state machine, one row per user.
`id`, `user_id` (FK, unique), `flow` (`candidate|employee|contact|null`),
`step` (text), `data` (jsonb), `updated_at`.

### Supply & demand

**`wa_companies`** — `id`, `name`, `normalized_name` (unique, `lower(trim(name))`),
`created_at`.

**`wa_advocates`** — `id`, `user_id` (FK), `company_id` (FK), `role_title`,
`status` (default `active`, check `active|pending|inactive`), `created_at`,
`updated_at`. Unique `(user_id, company_id)`. The advocate's email is the user's
`email`.

**`wa_applications`** — `id`, `candidate_user_id` (FK), `company_id` (FK),
`role_query`, `job_posting_url`, `resume_path`, `resume_filename`,
`status` (default `submitted`, e.g. `submitted|emailed`), `created_at`,
`updated_at`.

**`wa_application_recipients`** — `id`, `application_id` (FK), `advocate_id` (FK),
`email` (snapshot at send), `emailed_at`, `email_status` (`sent|failed`),
`error`. Per-advocate delivery tracking + retry.

### Ops & audit

**`wa_company_requests`** — `id`, `candidate_user_id` (FK), `company_name_raw`,
`normalized_name`, `reason` (`unknown_company|no_advocates`),
`resolved_company_id` (FK, nullable), `status` (default `open`), `created_at`.
Backfill queue; powers the "we'll add it, check back in ~24h" promise.

**`wa_inbound_messages`** — unchanged from PR1 (`message_sid` unique idempotency
key + audit fields).

**`wa_outbound_messages`** — `id`, `to_phone`, `body` (nullable),
`content_sid` (nullable), `twilio_sid`, `status`, `error`, `created_at`.

### Résumé storage

Private Supabase Storage bucket **`wa-resumes`**. Objects keyed
`applications/{user_id}/{uuid}.pdf`; path stored on
`wa_applications.resume_path`. Validation on receipt: content-type
`application/pdf`, size ≤ 5 MB.

## 6. Flows

Copy below is **illustrative draft tone** (light, original Ofoodiez voice). Final
strings live in `copy.py`. Language: English for v1 (see §13).

### Welcome (entry — first contact / "hi" / Back to Menu)
Send the **Welcome** template (buttons Candidate / Employee / Contact Us).
Payloads `PATH_CANDIDATE | PATH_EMPLOYEE | PATH_CONTACT` set `flow` and enter it.

### Registration (shared sub-flow — skipped for already-registered users)
Skipped when the user already has `first_name` + `email`.

1. `reg_intro` → Register-intro template (Register / Back to Menu); the Register
   tap accepts the Terms (links `/terms`).
2. `reg_first_name` → text.
3. `reg_last_name` → text.
4. `reg_email` → text, **validated**.
5. `reg_review` → Registration-review template (Confirm / Edit / Restart) with
   `name/phone/email` vars.
   - **Confirm** → persist user fields + `terms_accepted_at` → continue into the
     chosen path.
   - **Edit** → re-collect from `reg_first_name`. **Restart** → Welcome.

### ① Candidate (after registration)
1. `cand_company` → "which company?" (text) → normalize + match:
   - **found & ≥1 active advocate** → store `company_id` → `cand_role`.
   - **found, no active advocates** → insert `wa_company_requests(no_advocates)`
     → Company-not-found template (Try another / Back to Menu).
   - **not found** → re-prompt once ("check spelling, English, with/without
     spaces"); if still unmatched → `wa_company_requests(unknown_company)` →
     Company-not-found template.
2. `cand_role` → role text → store `role_query`.
3. `cand_job_link` → URL text, **validated** (https only, host required, ≤2048,
   reuse PR1-style canonicalization) → store `job_posting_url`.
4. `cand_resume` → expect PDF media (`NumMedia` ≥ 1, `application/pdf`). Download
   from Twilio `MediaUrl` (HTTP basic auth: Account SID / Auth Token) → validate
   type + size → upload to Storage → store `resume_path` / `resume_filename`.
   Non-PDF/text → re-prompt.
5. `cand_submit` → create `wa_application` (`submitted`) → find active advocates
   at company → for each: SendGrid email (résumé attached) + insert
   `wa_application_recipients` (`sent|failed`). Set application `emailed`. Reply
   success ("on its way to N advocate(s)").
6. `cand_explore_more` → Explore-more template (Yes, explore / Finish / Back to
   Menu). **Yes** → `cand_company` (registration retained). **Finish** →
   sign-off + reset conversation.

### ② Employee (after registration)
1. `emp_company` → company text → **get-or-create** `wa_companies`.
2. `emp_role` → role text → store.
3. `emp_confirm` → Employee-confirm template (Confirm / Edit / Back to Menu) with
   `company/role/email` vars. **Confirm** → create `wa_advocates` (`active`;
   idempotent on `(user_id, company_id)`) → success + offer another company.
   **Edit** → re-collect.

### ③ Contact Us
1. `contact_msg` → free text → forward to the operator via the existing Telegram
   bot (`TELEGRAM_USER_ID`) + log → confirmation + Back-to-Menu template.

### Cross-cutting
- **Back to Menu** (button payload `BACK_TO_MENU`, or typed `menu`/`restart`)
  resets the conversation from (almost) any step.
- **Returning users** skip registration.
- **Rate-limiting** from PR1 (≤ N inbound / 60 s per phone) applies; over-cap →
  silent.
- **Idempotency** from PR1: duplicate `MessageSid` → no reprocessing, no
  duplicate sends.
- Unknown free-text at a decision step → gentle re-prompt (don't advance).
- Body-length cap; all queries ORM-parameterized; unexpected media → nudge.

## 7. Integrations

### Twilio Content templates (created once; SIDs in env)
Welcome, Register-intro, Registration-review (`name/phone/email`),
Company-not-found (`company`), Explore-more, Employee-confirm
(`company/role/email`), Back-to-Menu. Quick-reply buttons are sent as **session
messages** (always within the 24-h user-initiated window), which generally need
no WhatsApp template *approval* — confirmed via a sandbox spike first.

### Outbound messaging
`twilio` SDK:
`Client(account_sid, auth_token).messages.create(messaging_service_sid=…, to=…, …)`
— `body=` for text, `content_sid=` + `content_variables=json(...)` for menus.
Every send logged to `wa_outbound_messages`.

### SendGrid
API key in env; **domain auth** for `ofoodiez.com` (SPF/DKIM CNAMEs in
Cloudflare DNS). From `referrals@ofoodiez.com`. On submit, one email per active
advocate: subject "New candidate for {role} at {company}", body (candidate name,
role, job link, short note), **résumé PDF attached**. Per-recipient result
recorded.

### Supabase Storage
Storage REST API with the **service-role key** (via `requests`, no heavy new
dep): upload résumé, download for attachment. Bucket private.

## 8. Configuration (env vars)

- **Existing:** `TWILIO_AUTH_TOKEN`, `TWILIO_WEBHOOK_URL`.
- **New:** `TWILIO_ACCOUNT_SID`, `TWILIO_MESSAGING_SERVICE_SID`,
  `WA_CT_WELCOME`, `WA_CT_REGISTER_INTRO`, `WA_CT_REGISTER_REVIEW`,
  `WA_CT_COMPANY_NOT_FOUND`, `WA_CT_EXPLORE_MORE`, `WA_CT_EMPLOYEE_CONFIRM`,
  `WA_CT_BACK_TO_MENU`, `SENDGRID_API_KEY`, `WA_FROM_EMAIL`, `SUPABASE_URL`,
  `SUPABASE_SERVICE_ROLE_KEY`.
- Thresholds (rate limit, max body length, max résumé size) reuse PR1's
  `config.py`.

## 9. Operator setup (one-time)

1. Create the 7 Content templates in Twilio → copy SIDs into env.
2. Confirm a sender on the Messaging Service (sandbox for testing now; production
   sender at launch).
3. SendGrid: account, API key, domain auth for `ofoodiez.com` (Cloudflare DNS),
   verify the from-address.
4. Supabase: create the private `wa-resumes` bucket; copy the project URL +
   service-role key.
5. Run the revised `whatsapp_bot/schema.sql` (tables + RLS) in Supabase.
6. Set all env vars in Render.
7. **Sandbox spike:** confirm a quick-reply template renders tappable buttons and
   the tapped payload returns to the webhook.

## 10. Security & privacy

- Inbound signature verification + idempotency reused from PR1; fail-closed.
- Résumés are PII; consent is captured at registration (Terms). Stored in a
  private bucket; shared only with **active** advocates at the **named** company,
  by email.
- Twilio / SendGrid / Supabase service secrets live only in Render env / the
  gitignored `.env`.
- RLS on all tables blocks the Supabase anon API; the bucket is private.
- URL validation (https only) for job links; PDF type/size validation for
  uploads.

## 11. Testing

- pytest + sqlite in-memory (PR1 harness). External services mocked at their
  wrappers: Twilio REST (messaging layer), SendGrid (emailer), Supabase Storage
  (storage), Telegram (contact).
- **State-machine unit tests** (no network): every flow's transitions;
  email/URL/PDF validation; Back-to-Menu/reset; returning-user skip;
  edit/restart.
- **Matching:** found + advocates; found + no advocates (→ request); not found (→
  retry then request); get-or-create company race.
- **Integration (test client):** signed inbound button payload → expected state
  transition + expected outbound calls (mock) + DB rows. Résumé upload (mock
  Twilio media + storage). Submission → advocate emails + recipient rows (mock
  SendGrid). Idempotency (duplicate `MessageSid`).
- **Invariant:** only `active` advocates are emailed; nothing is sent for
  unknown/empty companies.

## 12. Build phasing

v1 still equals all three paths; this is just the implementation order.

- **0. De-risk spike** — sandbox quick-reply buttons + payload round-trip.
- **A. Foundation** — revised data model + `schema.sql`; messaging layer;
  state-machine engine + `wa_conversations`; Welcome + routing + Back-to-Menu /
  reset.
- **B. Registration** sub-flow (+ returning-user skip).
- **C. Candidate** flow — matching + `wa_company_requests`, role, job link,
  résumé → Storage.
- **D. Submission + delivery** — applications, advocate matching, SendGrid +
  recipients.
- **E. Employee** flow.
- **F. Contact Us** (Telegram forward).
- **G. Hardening** — rate limits, `wa_outbound_messages`, error handling,
  observability, runbook.

## 13. Open questions / to confirm

1. **Language — DECIDED:** English-only for v1 (see §3.8); Hebrew deferred.
2. **Advocate moderation — DECIDED:** auto-active in v1, no approval gate (the
   `status` field still allows adding one later).
3. **Production sender:** buttons + emailing real advocates eventually need the
   approved production WhatsApp sender (Meta business verification — the long
   pole). The sandbox covers development. Unchanged from the old §6.
4. **Résumé retention:** any deletion/retention policy for stored résumés (PII)?
   Default: keep; revisit.
5. **Contact Us destination:** Telegram only, or also email you? Default Telegram.

## 14. Reuse from PR1

`/wa/webhook` (signature verify, `MessageSid` idempotency claim, audit row, fast
200), the `config.py` pattern, `copy.py`, the sqlite pytest harness +
`run_wa_local.py`, the `wa_companies` / `wa_users` / `wa_inbound_messages` tables
(users enriched), the RLS approach, and the engine-options DB hardening. Only
`wa_referral_links` and the synchronous-TwiML reply are dropped.
