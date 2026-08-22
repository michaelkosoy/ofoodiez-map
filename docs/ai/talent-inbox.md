# Talent Inbox — /admin/talent

A lightweight internal ATS / referral CRM: CVs arrive (Gmail or manual
upload), Gemini extracts a small structured profile and rates the candidate,
deterministic filtering + one AI call match them to companies, and every
referral (link / manual upload / email) is tracked. The dashboard + Postgres
are the SOURCE OF TRUTH; Gmail is only an ingestion source and outbound
transport. Code: `talent/` package (models, config, extract, matching,
ingest, emails, pipeline) + routes in `admin/talent.py` + templates
`app/templates/admin/talent*.html`.

## Routes (all behind admin auth)
Pages: `/admin/talent` (dashboard: counters, filters, search, bulk ops,
J/K/S/M/X keys; `?status=new` is the "New CVs" tab = candidates with NO action
taken: never reviewed AND never referred) · `/admin/talent/needs-action` ·
`/admin/talent/candidate/<id>` (review page: analysis, matches, referral
history, CV viewer, notes) · `/admin/talent/companies` ·
`/admin/talent/company/<id>` · `/admin/talent/ai` (usage/tokens) ·
`/admin/talent/cv/<id>/file` (the ONLY way a CV file is served — never
public URLs).
API: `/admin/api/talent/...` — sync, candidates (create/update/cv/analyze/
companies/quick-refer), match override, bulk, referrals (create/email-preview/
send-email/status), companies (create/update/find-candidates/
analyze-candidates).

## Quick actions (one pre-configured button per company)
`POST /api/talent/candidate/<id>/quick-refer {company_id}` acts per the
company's method, reusing an existing NEEDS_ACTION referral or creating one
(anything already progressed → 409 unless `force`):
- REFERRAL_LINK → sends the templated link email to the candidate
  IMMEDIATELY (deliberate exception to the preview rule — Ofir asked for
  one-click; the template is fully admin-configured per company).
- EMAIL → returns ref_id; the UI opens the prefilled compose (recipient
  fixed) so sending is one click.
- MANUAL_UPLOAD → returns the handoff pack: portal URL, instructions,
  copyable candidate details, and a ready **Claude-in-Chrome prompt**
  (`_claude_handoff_prompt`) that walks a Claude session through the portal
  submission (e.g. Zafran's Ashby: + Add → Referral), downloading the CV via
  the admin CV URL first and stopping before final submit.

## Scheduled ingestion (two paths, both keyed)
Keyed auth = admin session OR `?key=ADMIN_SECRET` / `X-Admin-Key` header,
fail-closed — same pattern as /wa/backfill-cron.
1. `POST /admin/api/talent/sync` — server-side IMAP pull (needs
   TALENT_GMAIL_* env). One call ingests everything new.
2. `POST /admin/api/talent/ingest` — push path for external routines: Ofir's
   scheduled Claude routine reads Gmail through a CONNECTOR (no app password,
   no server Gmail config) and POSTs each CV email here as multipart
   (file + from_email/from_name/subject/snippet/received_at/message_id).
   Idempotent on message_id (`ingested: false` = already known, not an
   error), so overlapping scan windows are safe; a repeat sender becomes a
   new CV version. This is the ACTIVE path — the routine prompt lives with
   Ofir's schedule, keep the endpoint contract stable.
Both paths return fast; AI analysis continues in a background thread.

## Personal CV copies
Every incoming CV (sync + manual upload) is best-effort mirrored to Google
Drive: `<TALENT_DRIVE_FOLDER_ID or GOOGLE_DRIVE_CV_FOLDER_ID>/Talent CVs/
<Candidate>/v<n>_<file>` via the CV reviewer's service account
(`pipeline.mirror_cv_to_drive`). Unconfigured Drive = silently skipped;
Postgres remains the durable store either way.

## Hard rules
- **AI never submits anything.** All outbound actions are two-step admin
  actions: preview (recipient FIXED from stored config, subject/body
  editable) → explicit send. No bulk sends exist on purpose.
- **Admin overrides survive AI re-runs**: `talent_matches.admin_fit` is
  separate from `ai_fit` and always wins; re-matching never touches it.
- **Referral `method` is a snapshot** taken at creation — editing a company's
  method later never rewrites history. Inactive companies stay in history but
  are excluded from new matching/recommendations.
- **Double-referral guard**: creating a referral for an existing
  candidate+company pair returns 409 unless `force` — the UI asks first.
- Candidate ids are UUIDs (PII behind admin URLs); private notes are never
  sent to companies or the AI.

## Cost discipline (Gemini)
- One central config: `talent/config.py`. `GEMINI_CV_EXTRACTION_MODEL` /
  `GEMINI_CV_MATCHING_MODEL` both default `gemini-3.5-flash-lite`;
  `GEMINI_CV_FALLBACK_MODEL` empty = disabled. Calls go through
  `cv_review.gemini.generate_json` (structured output, no tools).
- Text goes to Gemini, not files: PDFs are parsed locally with pypdf and DOCX
  with the cv_review sandbox (both inside the one-shot scrubbed/rlimited
  child — email attachments are untrusted). The raw PDF is sent inline ONLY
  when local extraction yields nothing (scanned).
- One analysis per CV version, cached on `talent_cvs` (model, extraction
  version, analyzed_at). Re-runs only on new CV / explicit Re-analyze.
- Matching = deterministic prefilter (`talent/matching.py: plausible`) →
  ONE call for the whole shortlist (≤15 companies). Reverse direction (new
  company → existing candidates) same shape: free scan → one call for the
  approved shortlist. Never one request per company.
- Every API call is logged to `talent_ai_log` (tokens/latency/outcome, never
  content) → `/admin/talent/ai`. Cost estimates reuse
  `cv_review.gemini.PRICES_PER_1M`; tokens are the ground truth.

## Gmail ingestion
`talent/ingest.py`, stdlib imaplib, READ-ONLY, app password
(`TALENT_GMAIL_USER`/`TALENT_GMAIL_APP_PASSWORD`, optional folder/window).
Idempotent: dedupes on Message-ID. Only emails with a PDF/DOCX attachment are
ingested (first CV-looking attachment wins); repeat senders become a new CV
VERSION on their existing card. Sync is a dashboard button (`POST
/admin/api/talent/sync`) — cron can hit the same endpoint later if wanted.
Analysis runs in a background thread (cv_review app-context pattern);
failures land on the CV row and the UI offers Re-analyze.

## Storage
All in Postgres via `talent/models.py` (auto-create through init_db;
`import talent.models` in app.py must stay BEFORE init_ig_automation):
`talent_companies` (referral method + per-method config + target profile +
templates), `talent_candidates` (status NEW/STRONG/MAYBE/SKIP/COMPLETED/
ARCHIVED — the S/M/X review verdict; AI's own rating lives in the analysis),
`talent_cvs` (file blob — prod disk is ephemeral, DB is the durable store),
`talent_emails`, `talent_matches`, `talent_referrals` (status NEEDS_ACTION/
WAITING/SUBMITTED/COMPLETED/CANCELLED + event log), `talent_ai_log`.

## Outbound email
`talent/emails.py` via Brevo (`BREVO_API_KEY` + `WA_FROM_EMAIL`, same as the
bot). Templates support only whitelisted `{vars}` via regex substitution —
no template code. `candidate_highlights` comes from the stored AI strengths,
never a fresh AI call. Missing transport/config → clean 400s, nothing breaks.

## Verify locally
Boot the app, log in to /admin, create a company, upload any PDF via
"+ Add Candidate". Without GEMINI_API_KEY the CV still ingests and text
extraction runs; analysis shows FAILED with a clear error and a Re-analyze
button. No automated tests by project convention.
