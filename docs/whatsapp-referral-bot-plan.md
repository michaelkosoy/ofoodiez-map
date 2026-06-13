# WhatsApp Referral-Link Bot — Implementation Plan

> **For agentic workers:** This is an engineering plan, not a line-by-line task script. Section 11 decomposes the work into PR-sized phases with files, code sketches, tests, and risks. Implement phase-by-phase with a review checkpoint between each.

**Goal:** Add a Twilio WhatsApp bot to the existing Ofoodiez Flask app that lets users search approved job-referral links by company and submit new links (held for human moderation), reusing the app's existing blueprint/DB/webhook patterns.

**Architecture:** A new `whatsapp_bot/` Flask blueprint (mirroring `instagram_automation/`) exposing one signed webhook that replies synchronously with TwiML. No queue, no Redis, no AI. State (selection context, rate-limit counters, idempotency keys, audit log) lives in four `wa_`-prefixed Postgres tables on the existing Supabase instance, created via SQL with RLS enabled.

**Tech Stack:** Flask 3.1 + Flask-SQLAlchemy 3.1 (existing shared `db`), `twilio` Python SDK (new dep), Supabase Postgres (existing), Gunicorn on Render (existing), pytest (new dev dep).

---

## 1. Executive Summary

The bot is a **reactive, user-initiated** WhatsApp service: a user texts a company name, gets a numbered list of up to 5 approved referral links (labelled by submitter first-name + role), and replies with a number to receive the link. Users contribute via `add <company> <url> [role]`; submissions are stored `pending` and never shown until a human flips them to `approved` in the Supabase Table Editor.

It fits the existing system with near-zero new infrastructure: it copies the proven `instagram_automation` blueprint pattern (`init_app(app)`, `url_prefix`, HMAC webhook verification, always-return-200), reuses the single shared `SQLAlchemy()` instance and the Supabase database already backing the popups feature, and runs inside the same Gunicorn process. The only new runtime dependency is the `twilio` SDK; the only new infra is four database tables.

**Three findings reshaped the naive design and are load-bearing throughout this plan:**

1. **Twilio inbound webhooks are at-most-once, not at-least-once.** Twilio makes one attempt (≈15 s timeout); on failure it calls the Fallback URL once, then gives up — there is no redelivery queue. The dominant production risk is therefore **message loss**, not duplicate processing. We mitigate loss with a paid always-on instance (confirmed), fast synchronous handlers, and a static Fallback TwiML Bin. We keep `MessageSid` idempotency anyway because it is cheap and covers the "handler finished but Twilio timed out at 15 s, user manually retries" case.

2. **`db.create_all()` never alters an existing table** (`instagram_automation/database.py:19-20`). It only creates missing tables. So the schema cannot be evolved from Python. We **create the tables via a one-time SQL script in the Supabase SQL editor, with RLS enabled, before the first deploy.** That same SQL-editor workflow is the migration mechanism for all future schema changes (run `ALTER` before merging the model change). This also eliminates the PII-exposure window that a "deploy then enable RLS" ordering would create.

3. **Reuse the existing shared `db`; do not instantiate a second `SQLAlchemy()`.** A second instance — or a second `db.init_app()` — raises `RuntimeError`. The new package imports `db` from `instagram_automation.database` and registers its models there.

Scale target (~5,000 users, reactive only) is comfortably met synchronously: every interaction is 1–3 indexed queries; realistic throughput at 8 gthreads is ~8–25 req/s, far above the offered load of a reactive bot. No queue is justified.

---

## 2. Current Codebase Analysis

**Framework & process model.** Flask 3.1.2 monolith. `app.py` (repo root) builds a single `Flask` app, registers the Instagram blueprint, and starts a Telegram bot in a daemon thread. `Procfile`: `web: gunicorn --workers 1 --threads 4 app:app`. **Workers are pinned to 1 deliberately** (commit `bcff1ef`) so the in-process Telegram `infinity_polling` loop doesn't duplicate. This is a hard constraint: any design that assumes multiple workers, or that relies on multiple workers for throughput, is wrong. We stay single-worker and bump threads.

**Deployment.** Render web service (`ofoodiez-map.onrender.com`), auto-deploy on push to `main`; `ofoodiez.com` fronted by Cloudflare. Confirmed **paid/always-on tier** — no cold-start risk against the 15 s webhook timeout, and zero-downtime deploys. No `ProxyFix` middleware is configured, so `request.url` reconstruction behind the proxy is unreliable → we pin the webhook URL for signature validation rather than reconstruct it.

**Database.** Flask-SQLAlchemy 3.1.1 + `psycopg2-binary`. `SQLALCHEMY_DATABASE_URI` comes from `IG_DATABASE_URL` or `DATABASE_URL` with a `postgres://`→`postgresql://` rewrite (`app.py:30-36`). In production this points at **Supabase Postgres** (the `home()` route loads popups from it). Schema is managed by `db.create_all()` at startup (`instagram_automation/database.py:11-20`) — **no Alembic, no migrations.** There is exactly one `db = SQLAlchemy()` (`database.py:8`); all models (`User`, `Contact`, …, `PopupEvent`) hang off it. Table naming convention: `ig_*` for Instagram, plus a bare `popup_events`. We follow with `wa_*`.

**Webhook precedent (the template to copy).** `instagram_automation/webhooks.py`: a GET verification handshake, a POST handler that verifies an HMAC-SHA256 signature with `hmac.compare_digest`, wraps per-item processing in try/except, and **always returns `200` fast**. This is exactly the shape our Twilio webhook should take (substituting Twilio's `RequestValidator` for Meta's HMAC).

**Blueprint pattern.** `instagram_automation/__init__.py` defines `ig_bp = Blueprint(..., url_prefix='/ig')` and an `init_app(app)` that imports submodules, calls `init_db(app)`, and registers the blueprint. `app.py:40-41` calls it. We mirror this precisely.

**Config & secrets.** Plain `os.environ.get(...)` with defaults, `python-dotenv` for local `.env`. No secret manager. Admin endpoints use a query-param shared secret (`/api/refresh?key=ADMIN_SECRET`, `app.py:507-511`).

**Logging.** `print()` with emoji everywhere — captured by Render's stdout log stream. No structured logging, no Sentry. We use Python `logging` to stdout (Render captures it identically) plus a durable audit row per message.

**Reuse inventory.**
- Shared `db` instance and the `init_app(app)` blueprint pattern → reuse directly.
- HMAC-webhook structure in `instagram_automation/webhooks.py` → copy shape, swap validator.
- Graceful-degradation precedent: `home()` (`app.py:200-211`) wraps a DB query in try/except with a static fallback → apply the same to the bot's DB-down path.
- `requests` is already a dependency; `twilio` is the only new runtime add.
- Supabase already in production → no new datastore.

**Risks/constraints carried from the current architecture.**
- **Single worker is mandatory** (Telegram polling). Throughput comes from threads only.
- **Thread-pool contention:** `/api/places` (`app.py:392-501`) does a synchronous Google-Sheets fetch + sequential geocoding on the same gthreads; a cache-expired hit can occupy a thread for tens of seconds and, under load, starve webhook handlers past Twilio's 15 s timeout. Bumping threads 4→8 mitigates; documented as a known limitation.
- **`create_all` can't migrate** → SQL-editor migrations (above).
- **No `SQLALCHEMY_ENGINE_OPTIONS`** today → no `pool_pre_ping`/`pool_recycle`; idle Supabase pooler connections go stale and the first message after a quiet period would hit a dead connection. We add engine options (benefits the whole app).
- **Pre-existing PostgREST exposure (freebie to fix):** tables in `public` are auto-exposed by Supabase's anon API with default grants. `ig_users` stores Instagram **access tokens** (`database.py:30`) and `popup_events` is public — both are reachable today via the anon key. The one-time RLS SQL should cover these existing tables too.

---

## 3. Recommended Architecture

**Component layout** — new package `whatsapp_bot/`, mirroring `instagram_automation/`:

```
whatsapp_bot/
  __init__.py     # wa_bp Blueprint (url_prefix='/wa') + init_app(app)
  config.py       # env reads: TWILIO_AUTH_TOKEN, TWILIO_WEBHOOK_URL, thresholds
  models.py       # SQLAlchemy models on the SHARED db (imported from instagram_automation.database)
  webhooks.py     # POST /wa/webhook: verify → claim SID → dispatch → reply TwiML
  parser.py       # deterministic, bilingual command parsing + URL validation/canonicalization
  services.py     # search, selection, submission, company-get-or-create, rate-limit
  copy.py         # bilingual (en/he) message strings
```

`parser.py` and `services.py` are split because the parser is pure (trivially unit-testable with no DB) while services touch the DB; keeping them apart keeps the pure logic test-fast. `copy.py` isolates the bilingual strings so adding/adjusting wording never touches logic.

**Request flow (synchronous, no queue):**

```
Twilio ──POST /wa/webhook (form-encoded)──▶ webhooks.webhook()
  1. RequestValidator.validate(pinned_url, form, X-Twilio-Signature)  ─ fail ▶ 403
  2. INSERT wa_inbound_messages(message_sid …) + COMMIT   ← idempotency claim + audit, FIRST
       └─ IntegrityError (duplicate SID) ▶ rollback, return empty TwiML 200
  3. handle_message(phone, body, profile, num_media)  ← all business logic, wrapped in try/except
       ├─ rate-limit COUNT(*) on wa_inbound_messages   ─ over ▶ empty TwiML (silent)
       ├─ parse → {help | add | select | search}
       ├─ search/select  ─ reads only status='approved'
       └─ submit         ─ validate URL, get-or-create company, INSERT pending link
  4. UPDATE the audit row (parsed_command, response_summary, processing_ms, error)
  5. return TwiML <Response>[<Message>…]</Response>
```

**Design choices & tradeoffs:**

- **Synchronous TwiML vs REST API + queue.** Synchronous. Each op is 1–3 indexed queries; well within the 15 s budget. A queue (Redis/celery) would add infra that violates "minimal" and buys nothing for a reactive bot at this scale. Tradeoff: a slow query blocks a gthread — mitigated by threads=8 and indexed queries. **Justified: no queue.**
- **Idempotency claim *before* processing, not after.** If the audit INSERT happened at the end, two concurrent deliveries of the same SID would both fully execute (double side effects) and only the second commit would fail. Claiming the SID first means the duplicate is rejected before any side effect. Reframed honestly: because inbound is at-most-once, duplicates are rare; this is cheap insurance, not the main reliability mechanism.
- **DB-backed selection state, not in-memory.** A user's "last search results" (the numbered list) is stored on `wa_users.last_results` (JSONB array of link IDs) + `last_results_at`, with a 30-minute TTL. Survives deploys/restarts; works regardless of which gthread handles the follow-up "2". No sticky sessions.
- **DB-backed rate limiting, not in-memory.** A `COUNT(*)` over `wa_inbound_messages WHERE from_phone=? AND created_at > now()-60s` (backed by the `(from_phone, created_at)` index) is one cheap query, is correct under restarts, and removes a whole module plus a worker-count caveat. (An in-memory sliding window would only be valid because workers=1 — fragile and not worth it.)
- **Reuse shared `db`; pre-create tables via SQL.** `whatsapp_bot.init_app` imports models (registering them on the shared metadata) and registers the blueprint. It does **not** call `db.init_app` (already done) and does **not** call `create_all` (tables pre-created via SQL). This sidesteps both the second-instance `RuntimeError` and the create-order trap.

---

## 4. Database Schema

Four tables, all `wa_`-prefixed, created by the **one-time SQL script below in the Supabase SQL editor before first deploy.** This script is also the canonical schema-of-record; future changes are `ALTER`s run here before the matching model edit is merged.

```sql
-- ============ whatsapp_bot schema (run once in Supabase SQL editor) ============

create table if not exists public.wa_companies (
    id              bigint generated by default as identity primary key,
    name            text not null,
    normalized_name text not null unique,          -- lower(trim(name)), language-as-typed
    created_at      timestamptz not null default now()
);

create table if not exists public.wa_users (
    id              bigint generated by default as identity primary key,
    phone           text not null unique,           -- E.164, NO 'whatsapp:' prefix
    profile_name    text,                            -- raw WhatsApp ProfileName
    last_language   text not null default 'en' check (last_language in ('en','he')),
    message_count   integer not null default 0,
    is_blocked      boolean not null default false,
    last_results    jsonb,                           -- array of wa_referral_links.id from last search
    last_results_at timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create table if not exists public.wa_referral_links (
    id                bigint generated by default as identity primary key,
    company_id        bigint not null references public.wa_companies(id),
    submitter_user_id bigint references public.wa_users(id),
    submitter_display text,                           -- first word of submitter's ProfileName
    role_title        text,
    url               text not null,                  -- cleaned, as shown to users
    url_canonical     text not null,                  -- for dedup
    status            text not null default 'pending'
                      check (status in ('pending','approved','rejected','expired')),
    rejection_reason  text,
    times_sent        integer not null default 0,
    reviewed_at       timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);
create index  if not exists ix_wa_links_company_status on public.wa_referral_links (company_id, status);
create index  if not exists ix_wa_links_pending        on public.wa_referral_links (status) where status = 'pending';
create unique index if not exists uq_wa_links_company_url_active
    on public.wa_referral_links (company_id, url_canonical) where status in ('pending','approved');

create table if not exists public.wa_inbound_messages (
    id               bigint generated by default as identity primary key,
    message_sid      text not null unique,            -- Twilio MessageSid → idempotency key
    from_phone       text not null,
    profile_name     text,
    body             text,
    num_media        integer not null default 0,
    parsed_command   text,                            -- help|add|select|search|ratelimited|error
    response_summary text,
    processing_ms    integer,
    error            text,
    created_at       timestamptz not null default now()
);
create index if not exists ix_wa_inbound_from_created on public.wa_inbound_messages (from_phone, created_at);

-- ============ Lock down PII from the Supabase anon/PostgREST API ============
-- RLS with NO policies blocks the anon & authenticated roles entirely.
-- The Flask app connects as the table OWNER (postgres role) which BYPASSES non-forced RLS,
-- so the app is UNAFFECTED. Do NOT use FORCE ROW LEVEL SECURITY (it would break the app).
alter table public.wa_companies        enable row level security;
alter table public.wa_users            enable row level security;
alter table public.wa_referral_links   enable row level security;
alter table public.wa_inbound_messages enable row level security;

-- Freebie: close pre-existing exposure of token/PII tables (verify column/table names first).
alter table public.ig_users     enable row level security;   -- holds Instagram access tokens
alter table public.popup_events enable row level security;
```

**Column/type notes.**
- `generated by default as identity` (not `always`) avoids any ORM-insert friction with SQLAlchemy.
- `status` is `text` + `CHECK`, not a native PG `enum`, because `create_all` cannot evolve enum types and we want the option to add states via a one-line `ALTER … DROP/ADD CONSTRAINT`.
- **Dedup partial unique** `uq_wa_links_company_url_active` allows the same URL to be re-submitted after a prior submission was `rejected`/`expired`, while blocking duplicates among live (`pending`/`approved`) rows.
- `wa_inbound_messages` intentionally **is** the webhook-event log; no separate `webhook_events` table (status callbacks are not enabled for MVP).

**SQLAlchemy models** (`whatsapp_bot/models.py`) mirror this DDL on the shared `db`:

```python
from datetime import datetime
from instagram_automation.database import db   # the ONE shared instance

class WaCompany(db.Model):
    __tablename__ = 'wa_companies'
    id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    normalized_name = db.Column(db.Text, nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WaUser(db.Model):
    __tablename__ = 'wa_users'
    id = db.Column(db.BigInteger, primary_key=True)
    phone = db.Column(db.Text, nullable=False, unique=True)
    profile_name = db.Column(db.Text)
    last_language = db.Column(db.Text, nullable=False, default='en')
    message_count = db.Column(db.Integer, nullable=False, default=0)
    is_blocked = db.Column(db.Boolean, nullable=False, default=False)
    last_results = db.Column(db.JSON)          # reassign whole list; never .append in place
    last_results_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class WaReferralLink(db.Model):
    __tablename__ = 'wa_referral_links'
    id = db.Column(db.BigInteger, primary_key=True)
    company_id = db.Column(db.BigInteger, db.ForeignKey('wa_companies.id'), nullable=False)
    submitter_user_id = db.Column(db.BigInteger, db.ForeignKey('wa_users.id'))
    submitter_display = db.Column(db.Text)
    role_title = db.Column(db.Text)
    url = db.Column(db.Text, nullable=False)
    url_canonical = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, default='pending')
    rejection_reason = db.Column(db.Text)
    times_sent = db.Column(db.Integer, nullable=False, default=0)
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Partial unique declared for parity if create_all ever runs on a fresh DB (e.g. sqlite tests):
    __table_args__ = (
        db.Index('uq_wa_links_company_url_active', 'company_id', 'url_canonical',
                 unique=True,
                 postgresql_where=db.text("status in ('pending','approved')"),
                 sqlite_where=db.text("status in ('pending','approved')")),  # BOTH dialects
    )

class WaInboundMessage(db.Model):
    __tablename__ = 'wa_inbound_messages'
    id = db.Column(db.BigInteger, primary_key=True)
    message_sid = db.Column(db.Text, nullable=False, unique=True)
    from_phone = db.Column(db.Text, nullable=False)
    profile_name = db.Column(db.Text)
    body = db.Column(db.Text)
    num_media = db.Column(db.Integer, nullable=False, default=0)
    parsed_command = db.Column(db.Text)
    response_summary = db.Column(db.Text)
    processing_ms = db.Column(db.Integer)
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

> **sqlite test note:** `postgresql_where` alone is silently dropped on sqlite, which would create a *full* unconditional unique index — making dedup tests pass for the wrong reason and resubmit-after-rejection tests wrongly fail. Supplying **both** `postgresql_where` and `sqlite_where` makes the partial index behave identically in tests and prod.

---

## 5. WhatsApp UX / Command Design

**Bilingual.** Per your choice, the bot detects the user's language per message and replies in kind. Detection is a cheap heuristic: any character in the Hebrew Unicode block (`U+0590–U+05FF`) → Hebrew; otherwise English. For signal-less messages (a bare digit like `2`), fall back to `wa_users.last_language` (updated on every message that carries a language signal; defaults to English). All strings live in `whatsapp_bot/copy.py` as `{'en': ..., 'he': ...}`.

**Commands (case-insensitive, trimmed):**

| Intent | Triggers | Notes |
|---|---|---|
| Help | `help`, `hi`, `hello`, `start`, `menu`, `עזרה`, `היי`, `שלום`, `התחל` | also sent on unrecognized empty/media-only input |
| Add | message starts with `add ` or `הוסף ` | `add <company> <url> [role]` |
| Select | the message is a lone integer `1`–`5` | indexes into `last_results` (TTL 30 min) |
| Search | anything else non-empty | the whole trimmed body is the company query |

**Search — found (English message):**
```
User: Google
Bot:  Found 3 referral links for Google:
      1. Alice – SWE
      2. Bob – Backend
      3. Charlie – PM
      Reply with the number to get the link.
```
**Search — found (Hebrew message):**
```
User: גוגל
Bot:  נמצאו 3 קישורי הפניה ל-גוגל:
      1. Alice – SWE
      2. Bob – Backend
      3. Charlie – PM
      השב/י עם המספר כדי לקבל את הקישור.
```
**Search — not found:**
```
User: Wingflow
Bot:  No referral links found for Wingflow.
      You can add one by sending:
      add Wingflow https://…
```
**Select:**
```
User: 2
Bot:  Bob – Backend at Google:
      https://company.jobs/referral/abc123
```
**Add — accepted:**
```
User: add Google https://company.jobs/referral/abc123 Backend
Bot:  Thanks — your referral link for Google was submitted for review. ✅
```
**Add — duplicate:**
```
User: add Google https://company.jobs/referral/abc123
Bot:  That link is already on file for Google (live or under review). 🙌
```
**Help:**
```
Bot:  Ofoodiez Referrals 💼
      • Send a company name to find referral links (e.g. Google)
      • Reply with a number to get a link
      • Add a link: add <company> <url> [role]
```

**Edge cases & exact behavior:**
- **Multi-word company in `add`:** tokens between the keyword and the first URL-shaped token are the company; tokens after the URL are the role. `add Goldman Sachs https://… Analyst` → company "Goldman Sachs", role "Analyst".
- **`add` with no URL:** reply with the `add` usage hint (don't create anything).
- **Media-only message** (`NumMedia` > 0, empty `Body`): treat as unrecognized → help. (No image processing in MVP.)
- **Bare digit but no/expired `last_results`:** reply "No recent search — send a company name first," not a search for the literal "1".
- **Digit out of range** (e.g. `9` when 3 results): reply "Please reply with a number between 1 and 3."
- **`From` field** arrives as `whatsapp:+9725…` → strip the `whatsapp:` prefix before storing/looking up the phone.
- **Smart quotes / angle brackets / trailing punctuation** around a pasted URL are stripped before validation.
- **Rate-limited / duplicate / over-cap:** silent (empty TwiML) where a reply would risk a loop; explicit friendly text where it aids the user (caps, validation).

---

## 6. Twilio WhatsApp Integration

**Account & sender setup (operator checklist — Michael does this; start now, it's the longest pole).** Tailored to the confirmed setup: existing Twilio account with billing; reuse the **existing Meta Business Manager** (the one behind the Instagram app), which is **not yet business-verified**; **the production sender number is deferred — the user prefers not to buy a Twilio number** (see step C).

*Progress (2026-06-13):* Twilio account credentials are in hand (the Auth Token is being **rotated** after exposure in chat, then stored in the gitignored `.env` / Render env — never in this doc or git). **Sandbox is live:** test phone `+972546824120` is joined to Twilio's shared sandbox sender `+14155238886`, giving a working WhatsApp test channel for all development. Remaining: step A (Meta verification, in progress) and step C (production sender number, deferred to launch).

- **A. Meta business verification — START FIRST (days–weeks; gates go-live).** `business.facebook.com` → Business Settings → Security Center → **Start verification**; submit legal business details + documents. Everything else can be wired while this is pending, but the sender can't fully launch (or raise messaging limits) until it clears.
- **B. Connect WhatsApp in Twilio.** Console → Messaging → Senders → **WhatsApp senders** → *Create new sender*; in the embedded signup, log in with the Facebook account that owns the existing Business Manager and **select that existing Business Manager** (do not create a new one). Create/select a **WhatsApp Business Account (WABA)** under it.
- **C. Production sender number — deferred to launch (user prefers not to buy).** A WhatsApp **API** sender number is *dedicated*: it cannot also be a personal or WhatsApp-app number. Two options, decided at launch — **(1)** bring a **spare number the user already owns** (dedicated to the bot, able to receive an SMS/voice code, not currently on any WhatsApp account), or **(2)** buy a cheap Twilio number as fallback. The personal number `+972…` is **not** a candidate (it would lose personal WhatsApp). Register the chosen number, complete the code, set **display name** "Ofoodiez Referrals" (Meta reviews this). Not needed until launch — the sandbox covers development.
- **D. Messaging Service (recommended wrapper).** Console → Messaging → Services → create one ("Ofoodiez WhatsApp"), add the sender to its pool, and set its inbound webhook to `POST https://ofoodiez-map.onrender.com/wa/webhook`. Set the **Fallback URL** to a static **TwiML Bin** with the friendly "try again in a moment" message. (Wrapping in a Messaging Service lets us swap numbers later without re-pointing the webhook.)
- **E. Sandbox for our own testing — DONE (2026-06-13).** Test phone `+972546824120` is joined to Twilio's shared sandbox sender `+14155238886`. Its inbound webhook gets pointed at the local ngrok URL (during local dev) or the prod URL (Phase 3) once the server exists. Use this for the manual checklist until the production sender clears.
- **F. Credentials & env vars.** `TWILIO_AUTH_TOKEN` — the (rotated) account Auth Token; `RequestValidator` validates inbound signatures with it. It lives **only** in the gitignored `.env` locally and Render env in prod — never in this plan or git; `.env.example` gets a placeholder only. `TWILIO_WEBHOOK_URL` — the exact public webhook URL. (Sender number / Messaging Service SID only matter if we later send via REST — not for MVP TwiML.) *Status: account credentials obtained 2026-06-13; Auth Token rotation pending after chat exposure.*

**SDK & dependency.** Add `twilio` to `requirements.txt` (pin a current version, e.g. `twilio==9.4.1`; verify latest at implementation time). Used for two things only: `twilio.request_validator.RequestValidator` (inbound signature check) and `twilio.twiml.messaging_response.MessagingResponse` (reply building). No outbound REST calls in MVP.

**Env vars** (Render dashboard + `.env.example`):
```
TWILIO_AUTH_TOKEN=...                 # from Twilio console; used for signature validation
TWILIO_WEBHOOK_URL=https://ofoodiez-map.onrender.com/wa/webhook   # PINNED, exact
# (TWILIO_ACCOUNT_SID / sender number only needed if/when we send via REST; not for MVP)
```

**Webhook config (Twilio console).** Point the WhatsApp number's "When a message comes in" to `POST https://ofoodiez-map.onrender.com/wa/webhook` — **the Render origin directly, bypassing Cloudflare** (Cloudflare Bot Fight Mode/WAF can 403 non-browser POSTs, and it adds a host-mismatch risk for signature validation). Set the **Fallback URL** to a static **TwiML Bin** returning a friendly "We're having a hiccup, try again in a moment 🙏" — this is the only safety net when the primary errors or times out (at-most-once: no auto-retry).

**Signature verification** (`whatsapp_bot/webhooks.py`):
```python
from twilio.request_validator import RequestValidator

def _verify_twilio_signature(req) -> bool:
    token = WaConfig.TWILIO_AUTH_TOKEN
    if not token:
        return False                                  # fail closed
    validator = RequestValidator(token)
    signature = req.headers.get('X-Twilio-Signature', '')
    return validator.validate(WaConfig.TWILIO_WEBHOOK_URL, req.form.to_dict(), signature)
```
We pass the **pinned** `TWILIO_WEBHOOK_URL` (not `request.url`) because there is no `ProxyFix` and Render/Cloudflare rewrite scheme/host, which would break HMAC validation.

**Reply pattern: TwiML, not REST.** Synchronous TwiML keeps us inside the user-initiated 24-hour service window with zero outbound API calls:
```python
from flask import Response
from twilio.twiml.messaging_response import MessagingResponse

def _twiml(text: str) -> Response:
    resp = MessagingResponse()
    if text:                       # empty body => no <Message> => Twilio sends nothing (silent)
        resp.message(text)
    return Response(str(resp), mimetype='application/xml')
```

**Messaging window & fees (state once, design is compliant).** Every interaction is user-initiated, so replies are free-form *service* messages inside the 24 h window — **no Meta template required and no per-message Meta conversation fee** (service conversations are free as of Nov 2024; the 2025 per-message pricing applies to template/business-initiated traffic, which we never send). Twilio's per-message carrier fee (~$0.005) applies in both directions; a search+select flow is ~4–5 billed messages. WhatsApp messaging-limit tiers (250/1k/10k unique recipients per day) constrain *business-initiated* messaging only — a purely reactive bot is exempt.

**Sandbox → production migration.** The Twilio **sandbox is for our own testing only**: it requires a join keyword, **participation expires after 72 hours** (users silently fall out and must re-join), throughput is ~1 msg/s, and the number is shared. Therefore **external beta runs on the production sender, not the sandbox.** Apply for the production WhatsApp sender **first** (Meta business verification is the longest pole — see Phase 0). Cutover from sandbox to production is a *number change*: sandbox testers do not migrate, and the production number must not already be registered to another WhatsApp app.

---

## 7. Scalability & Fault Tolerance

**Traffic / concurrency.** Single Gunicorn worker (mandatory), **threads bumped 4 → 8** in the `Procfile`. I/O-bound handlers (1–3 Supabase round-trips each) yield ~8–25 req/s sustained — comfortably above a reactive 5k-user bot's offered load, with Gunicorn's listen backlog absorbing short bursts. No queue.

**Reliability — failure modes & responses:**
- **At-most-once inbound (loss risk):** mitigated by always-on paid instance (no cold start vs 15 s timeout), fast handlers, and the static Fallback TwiML Bin. Accept rare loss; do not build a redelivery system.
- **Duplicate delivery (rare):** `MessageSid` UNIQUE; the SID is claimed (INSERT+commit) *before* any side effect, so a duplicate returns empty TwiML with zero reprocessing.
- **Supabase down / connection dropped:** the entire `handle_message` body is wrapped in try/except; on failure the bot returns a friendly static apology in the user's language (mirrors the `home()` fallback pattern). `pool_pre_ping=True` + `pool_recycle=1800` (new `SQLALCHEMY_ENGINE_OPTIONS`) prevent stale-connection errors after idle periods.
- **Partial failure mid-handler:** the audit row is already committed (step 2), so even a crash leaves a debuggable trace with the `error` column populated in the `finally` block.
- **Request timeout:** handlers target < 1 s; the 15 s Twilio budget is generous. The known risk is gthread starvation by `/api/places` geocoding — documented; threads=8 mitigates.

**Performance.**
- **Indexing:** `wa_companies.normalized_name` UNIQUE (exact-match search); `(company_id, status)` (list approved links for a company); partial `(status) WHERE pending` (moderation queue scans); `(from_phone, created_at)` (rate-limit COUNT + per-user history). All listed queries are index-covered.
- **Query shape:** search is 1 indexed lookup (+ 1 fallback ILIKE only on miss). Selection is 1 PK fetch. Submission is 2–3 short statements in one transaction. No N+1.
- **Caching:** none needed for MVP — the data is small and queries are sub-millisecond on indexes. (A future read-through cache of `approved` links per company is possible but YAGNI now.)
- **Async vs sync:** **sync.** Async would fight Flask 3 / Flask-SQLAlchemy / psycopg2 sync stack and the single-worker Telegram constraint for no benefit at this scale.

**Safety.**
- **Rate limiting:** ≤ 10 inbound messages per phone per rolling 60 s via the indexed COUNT; the 11th is silently dropped (empty TwiML, no loop).
- **Spam / submission caps:** ≤ 5 `pending` submissions per user and ≤ 20 submissions per user per day, enforced by cheap COUNTs before insert.
- **Malicious input:** body length capped; parser is deterministic with no eval/templating; all queries are ORM-parameterized (no SQL injection); media ignored.
- **URL validation:** `https` scheme only (reject `http`, `javascript:`, `data:`, `ftp`); host required; no `userinfo@` (anti-phishing/credential-smuggling); length ≤ 2048; fragment stripped; **query string kept** (referral codes live there).
- **Deduplication:** canonical URL (lowercased scheme+host, fragment dropped, query kept, empty path → `/`) under the partial unique index; concurrent identical submissions resolve via caught `IntegrityError`.
- **Concurrency correctness:** company get-or-create and link insert both use the catch-`IntegrityError`-rollback-refetch pattern, so races degrade to a graceful "already submitted" rather than a 500.

---

## 8. Moderation Plan

**MVP (your choice): Supabase Table Editor.** Zero code. Moderate by opening `wa_referral_links`, filtering `status = 'pending'` (the partial `ix_wa_links_pending` index makes this instant), and editing `status` to `approved` or `rejected` (optionally filling `rejection_reason`). Because the only query path that surfaces links filters `status = 'approved'` — **including the selection path, which re-checks status at send time** — nothing pending is ever exposed, even mid-flow.

A short runbook (added in Phase 4) documents: the filter to use, the allowed status values, the dedup implication (rejecting frees the URL for resubmission; the row can be deleted or left as `rejected`), and a weekly "review the queue" reminder.

**Optional, deferred (not in MVP scope):** ping the existing Telegram bot (`telegram_bot`, already wired to `TELEGRAM_USER_ID`) with a one-line notification on each new `pending` submission. This is a small, isolated add (~15 lines, reusing the existing bot instance) and is listed as a fast-follow, not built now.

---

## 9. Testing Strategy

Introduce **pytest** as a dev-only dependency (`requirements-dev.txt` or a Poetry/pip dev group; the repo currently has only ad-hoc root scripts). Tests run against **sqlite in-memory** via the Flask test client; the partial-index dialect note in §4 makes sqlite faithful for dedup.

**Unit (pure, no DB):**
- **Parser matrix** — table-driven cases covering: English search, Hebrew search, `help`/`עזרה`, `add` with 2-word and multi-word company, `add` with role, `add` without URL, bare digit, digit out of range, media-only, `whatsapp:` prefix stripping, smart-quoted URL, empty body, leading/trailing whitespace. Assert `(command_type, company, url, role, language)`.
- **URL validation/canonicalization** — accept `https://…?ref=abc`; reject `http://`, `javascript:`, `data:`, missing host, `https://user:pass@host`, > 2048 chars; assert fragment dropped, query kept; assert two trailing-slash/case variants canonicalize equal.

**Integration (Flask test client + sqlite):**
- **Signature** — compute a *real* valid `X-Twilio-Signature` with `RequestValidator(test_token)` against the pinned URL → 200; tamper a field → 403; missing `TWILIO_AUTH_TOKEN` → 403 (fail-closed).
- **Idempotency / replay** — POST the same `MessageSid` twice → second returns empty TwiML, exactly one `wa_inbound_messages` row, side effect (e.g., a submission) happened once.
- **Search & selection happy paths** — seed companies/links; assert numbered list and that `2` returns the 2nd link's URL and increments `times_sent`.
- **Submission** — accepted path creates a `pending` row with correct `submitter_display` (first word of ProfileName); duplicate canonical URL → graceful "already on file"; caps (6th pending rejected; 21st daily rejected).
- **Company race** — two get-or-create calls for the same normalized name yield one row (simulate by inserting then calling).
- **Rate limit** — 11 messages in < 60 s → 11th dropped (empty TwiML).

**Reliability / invariant:**
- **Pending-never-shown invariant** — seed `pending`, `approved`, `rejected`, `expired` links for one company; assert that across search output *and* every selection index, only `approved` URLs are ever emitted. This is the single most important test (it's the core safety guarantee).
- **Duplicate-delivery** — covered by the idempotency test above.
- **Burst** — a ~20-line pytest (mark `slow`) firing N concurrent signed POSTs from M phones via threads; assert all return 200 and row counts are consistent (no crashes, no double-processing).

**Manual checklist (Twilio sandbox, our own phone):**
1. Join sandbox; send `help` (EN) and `עזרה` (HE) → correct language replies.
2. Search a seeded company → numbered list; reply a valid number → link; reply `9` → range error.
3. Search unknown company → "not found" + add hint.
4. `add <co> <url> <role>` → "submitted"; repeat → "already on file".
5. `add` a bad URL (`http://`, junk) → validation message.
6. Approve the pending link in Supabase; re-search → it now appears.
7. Send 12 messages fast → later ones silently dropped.
8. Re-send a message Twilio already delivered (resend from console) → no double submission.

---

## 10. Rollout Strategy

**Phase 0 — prerequisites (no code; start immediately):**
- **Start the Twilio/Meta setup now per the §6 operator checklist.** The gating item is **Meta business verification** (the existing Business Manager from the IG app isn't verified yet; days–weeks). Twilio account exists and the **sandbox is already live** for development; the **production sender number is deferred to launch** (user prefers a spare owned number over buying). The sender can't launch until verification clears, so this runs in parallel with all code work.
- Confirm Render **paid/always-on** (done) and that auto-deploy on `main` is acceptable (it is, given zero-downtime on paid).
- Decide webhook host = **Render origin direct** (bypass Cloudflare).
- **Run the §4 SQL script in Supabase** (tables + indexes + RLS) so the schema exists with PII locked down *before* any code deploys. *Risk:* getting RLS wrong could either expose PII (forgot to enable) or break the app (used `FORCE`). Verify the app still reads/writes after enabling (it connects as owner → unaffected).

**Phase 1 — local development:** `flask run` + `ngrok http 5000`; point a **Twilio sandbox** number at the ngrok URL. *Risk/gotcha to document:* running `app.py` locally with `TELEGRAM_BOT_TOKEN` set will **steal production Telegram polling** (409 conflicts) — unset it locally or use a separate dev token.

**Phase 2 — Twilio sandbox (self-test):** exercise the full manual checklist on our own phone via the sandbox. *Risk:* sandbox 72 h expiry and 1 msg/s — fine for self-test, not for users.

**Phase 3 — production deploy, feature dormant:** merge code to `main` (auto-deploys). The webhook is live but **no number is pointed at it yet for users**, so the feature is invisible. Verify `/wa/webhook` returns 403 to unsigned requests and the startup log asserts `TWILIO_WEBHOOK_URL == configured`.

**Phase 4 — small beta on the *production* sender:** once the production sender is approved, point it at the prod webhook and onboard a handful of known users. *Risk:* this is the first real-user exposure — watch logs/audit rows for unexpected parses, errors, and latency. (Beta does **not** run on the sandbox — testers would drop every 72 h.)

**Phase 5 — scale to thousands:** open the number more widely. The synchronous design + indexes carry it; the only thing to watch is gthread contention with `/api/places`. *Risk:* a viral spike — Gunicorn backlog + at-most-once means extreme bursts could drop some messages; acceptable for this product, and the Fallback Bin gives users a retry prompt.

---

## 11. Implementation Phases

PR-sized, each independently deployable and testable. Ordered so no PR ships a dead/half-wired code path, and so the schema is never frozen before its consumers exist (per the `create_all` limitation). Phase 0 above is prerequisite (no code).

### PR 1 — Skeleton + models + webhook + signature + idempotency + audit (the "echo" bot)

**Goal:** A live, signed, idempotent, logged webhook that replies with a static bilingual help message. No search/submit yet — but fully safe and observable.

**Files:**
- Create: `whatsapp_bot/__init__.py`, `config.py`, `models.py`, `webhooks.py`, `copy.py`
- Modify: `app.py` (add `SQLALCHEMY_ENGINE_OPTIONS` before IG init; register `wa_bp` after it), `requirements.txt` (`twilio`), `.env.example` (Twilio vars), `DEVELOPER_README.md` (Twilio integration entry)
- Test: `tests/whatsapp_bot/test_webhook.py`, `tests/conftest.py`

**Implement:**
- `app.py` — set engine options *before* `init_ig_automation(app)` (which calls `db.init_app`), then register the bot:
  ```python
  app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True, 'pool_recycle': 1800}
  # ... existing init_ig_automation(app) ...
  from whatsapp_bot import init_app as init_wa_bot
  init_wa_bot(app)
  ```
- `whatsapp_bot/__init__.py` — `wa_bp = Blueprint('whatsapp_bot', __name__, url_prefix='/wa')`; `init_app` imports `models` and `webhooks`, registers the blueprint, does **not** touch `db.init_app`/`create_all`.
- `models.py` — the four models from §4 on the shared `db`.
- `webhooks.py` — `POST /wa/webhook`: verify signature (§6) → claim SID (INSERT+commit `wa_inbound_messages`, catch `IntegrityError` → empty TwiML) → `try` reply = static help; `except` → log + apology, set `error`; `finally` set `processing_ms`, commit → `_twiml(reply)`.
- `config.py` — `TWILIO_AUTH_TOKEN`, `TWILIO_WEBHOOK_URL`, thresholds.

**Tests required:** signature valid/invalid/missing-token; duplicate SID → one row + empty TwiML; valid signed message → 200 with `<Message>`; audit row populated with `processing_ms`.

**Risks:** shared-`db` import order (mitigate: `init_wa_bot` runs after `init_ig_automation`); engine-options placement (must precede `db.init_app`).

**Outcome:** Texting the sandbox number returns the help message; every inbound is verified, deduped, and logged.

### PR 2 — Parser/router + help + search + selection

**Goal:** Real lookups. Company search returns numbered approved links; a number returns the link.

**Files:** Create `whatsapp_bot/parser.py`, `services.py`; add search/select strings to `copy.py`. Modify `webhooks.py` (call `handle_message`). Test: `tests/whatsapp_bot/test_parser.py`, `test_search.py`.

**Implement:** `parser.py` — `detect_language`, `parse(body)` → intent + fields (§5), bilingual command words. `services.py` — `handle_message(...)` orchestrator; `search_company(query, lang)` (normalized exact → ILIKE contains → first-token; **only `status='approved'`**; top 5; write `last_results`/`last_results_at`/`last_language` via whole-list reassignment); `select_result(user, n)` (TTL 30 min; re-verify `approved` at send; increment `times_sent`). Rate-limit COUNT guard at the top of `handle_message`.

**Tests required:** parser matrix (§9); search found/not-found; selection valid/expired/out-of-range; **pending-never-shown invariant**; rate-limit drop.

**Risks:** JSON `last_results` in-place mutation not tracked (always reassign); TTL/language fallback for bare digits.

**Outcome:** End-to-end search → select works for approved links in both languages.

### PR 3 — Submission + URL validation + dedup + caps

**Goal:** Users submit links; stored `pending`; duplicates and spam blocked.

**Files:** Add `validate_and_canonicalize` to `parser.py`; add `submit_link`, `get_or_create_company` to `services.py`; add submission strings to `copy.py`. Test: `test_submission.py`, extend `test_parser.py` (URL cases).

**Implement:** URL validation/canonicalization (§7). `get_or_create_company` and `submit_link` with catch-`IntegrityError`-rollback-refetch; caps (≤5 pending, ≤20/day) via COUNT; `submitter_display` = first word of `ProfileName`.

**Tests required:** URL accept/reject/canonical-equality; accepted submission creates `pending` row; duplicate → graceful; caps enforced; company race → one row.

**Risks:** dedup partial-index dialect (both `*_where` set, §4); multi-word company tokenization.

**Outcome:** `add …` works, moderated queue fills, no duplicates/spam.

### PR 4 — Procfile threads, runbook, observability polish, burst test

**Goal:** Production hardening and operator docs.

**Files:** Modify `Procfile` (`--threads 4` → `--threads 8`, **its own commit** for attributability on the shared monolith); add `whatsapp_bot/RUNBOOK.md` (moderation steps, env vars, Twilio console config, Fallback Bin text, common failures); ensure structured `logging` line per request. Test: `test_burst.py` (mark `slow`).

**Tests required:** burst of concurrent signed POSTs → all 200, consistent row counts.

**Risks:** threads bump interacts with the whole monolith (Telegram thread, `/api/places`) — isolated commit eases rollback.

**Outcome:** Documented, observable, burst-tested service.

### PR 5 — Production sender cutover

**Goal:** Go live for real users on the approved production number.

**Files:** None (Twilio console + Render env only). Point the production sender at the prod webhook; set `TWILIO_WEBHOOK_URL` accordingly; configure the Fallback URL.

**Tests required:** manual checklist (§9) on the production number; confirm startup URL-assertion log.

**Risks:** number must be un-bound from other apps; sandbox testers don't migrate; first real exposure — monitor audit rows.

**Outcome:** Public, reactive WhatsApp referral bot.

---

## 12. Open Questions

1. **Supabase connection mode/port (affects pool sizing).** Is prod's `DATABASE_URL`/`IG_DATABASE_URL` using the Supavisor pooler in **transaction mode (6543)** or **session mode**, or a **direct 5432** connection? Render has no outbound IPv6, so direct 5432 (IPv6-only without the add-on) is unlikely — but confirm the port. Session-mode pooling pins server connections (~15 on free tier) and the default pool (5+10) plus the Telegram thread could exhaust them. *Action: read the Render env value; if needed, set a conservative `pool_size`/`max_overflow` in `SQLALCHEMY_ENGINE_OPTIONS`.*
2. **App connects as table owner (RLS assumption).** Confirm the Flask DB role bypasses non-forced RLS (standard for Supabase `postgres` role). *Action: after running the RLS SQL, verify the app still reads/writes; never enable `FORCE ROW LEVEL SECURITY`.*
3. **Production sender — UPDATED (2026-06-13).** Reuse the **existing Meta Business Manager** (from the Instagram app); it is **not yet business-verified** — verification is the long-pole prerequisite, now in progress (§6 step A). **Number: deferred to launch.** The user prefers **not to buy** a Twilio number; preferred path is bringing a **spare number they own**, dedicated to the bot (a WhatsApp API number can't double as personal WhatsApp), with a bought Twilio number as fallback. Open sub-question: does the user have a suitable spare number? Revisit at launch — does not block development (the sandbox covers it). Full setup in §6.
4. **Extend RLS to existing tables now?** Recommend yes — `ig_users` exposes access tokens and `popup_events` is public via the anon API today. Confirm including them in the one-time SQL is in scope. (Separately: a real Google Maps key is committed in `docs/DEPLOYMENT.md:38` and a default admin secret ships in `app.py:508` — worth rotating, out of scope for this feature.)
5. **Thresholds — confirm defaults:** 10 msg/min rate limit; 5 pending + 20/day submission caps; 30-min selection TTL; top-5 results.
6. **Hebrew command aliases — confirm keywords:** `הוסף` for `add`, `עזרה`/`היי`/`שלום`/`התחל` for help. Any others?
7. **Cross-language company matching.** MVP matches the company name as typed (a link added as "Google" won't be found by searching "גוגל"). Acceptable for MVP, or do we need an alias map? (Recommend defer.)
8. **Telegram moderation ping.** Build the optional new-submission Telegram notification as a fast-follow after MVP, or leave moderation purely dashboard-driven?
