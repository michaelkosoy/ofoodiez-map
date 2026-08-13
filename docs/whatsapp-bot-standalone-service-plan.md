# WhatsApp bot as a standalone, scalable Render service (same repo, same Supabase)

> Saved plan. In a new session, "use the new service plan" refers to this file.

## Context

The bot runs *inside* the main Ofoodiez app today (`app.py` → `init_wa_bot(app)`),
sharing a process with the website, the Telegram polling thread, Google Maps
geocoding and Instagram automation. The goal is to run it on its **own Render
service** (same repo, new entry point, **no new domain** — the default
`*.onrender.com` URL is fine) **so it can scale independently to ~3,000 users**.
Render **free tier**.

The good news: the bot is already built for this.
- **Stateless app:** all conversation state lives in Postgres (`wa_conversations`),
  and the webhook is **idempotent** (`wa_inbound_messages.message_sid` UNIQUE). So
  the process holds no per-user memory → it scales horizontally with zero code change.
- **Replies are sent via the Twilio REST API, not TwiML** → the webhook can return
  `200` instantly and do all work off the request path, fully decoupling from
  Twilio's ~15 s webhook timeout.
- Only coupling to the rest of the repo is the shared `db` (`from database.models
  import db`, which imports only `datetime`+`flask_sqlalchemy`); the bot uses none
  of the site models. Self-heals its own `wa_` schema at boot (`migrate.py`).

**Reality check on "3k users + free tier":** 3k *registered* users is not 3k
concurrent. WhatsApp traffic is bursty but low-rate (a handful of msgs/sec at peak),
and the bot is **I/O-bound, not CPU-bound** (string ops + DB + HTTP). One small
instance handles that fine. The free-tier risks are **(a) spin-down cold starts
dropping the first webhook**, **(b) the slow résumé→upload→email path blocking
threads**, and **(c) the 750 instance-hours/month budget**. The architecture below
targets exactly those.

## Target architecture

```
 Twilio WhatsApp ──POST /wa/webhook──▶ [Render free web service: wa_wsgi:app]
                                         gunicorn -k gthread, 1 worker, ~4 threads
   (1) verify signature (pinned URL)
   (2) claim idempotency row + COMMIT        ← fast, synchronous
   (3) submit(process, inbound) ▶ ThreadPoolExecutor (in-proc, ~8 workers)
   (4) return empty TwiML 200  ◀── instant ack (never waits on downstream)
                                         │
   background thread (app context): router.handle → Twilio REST reply,
        Supabase résumé upload, Brevo email, audit-row finalize
                                         │
 Supabase Postgres (SAME project, via transaction pooler :6543)  ◀── shared state
 + external uptime pinger ──GET /wa/healthz every ~10 min──▶ keeps the instance warm
```

Stateless + idempotent + Postgres-backed state means: to grow past one instance
later you just raise Render's instance count / plan — no redesign.

## Phase 1 — Stand up the standalone service (gets it live & warm)

1. **New entry point `wa_wsgi.py` (repo root)** — a Flask app with *only* the bot,
   binding `db` before `init_wa_bot` (so startup migrations run on a live session):
   ```python
   import os
   from flask import Flask
   from dotenv import load_dotenv
   from database.models import db
   from whatsapp_bot import init_app as init_wa_bot
   load_dotenv()
   app = Flask(__name__)
   _url = os.environ.get("DATABASE_URL") or os.environ.get("IG_DATABASE_URL")
   if _url and _url.startswith("postgres://"): _url = _url.replace("postgres://","postgresql://",1)
   app.config["SQLALCHEMY_DATABASE_URI"] = _url or "sqlite:///wa_local.db"
   app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
   app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
       "pool_pre_ping": True, "pool_recycle": 1800,
       "pool_size": 5, "max_overflow": 5,   # modest: stay within Supabase pooler limits
   }
   db.init_app(app)        # bind only; do NOT create_all (site tables already exist)
   init_wa_bot(app)        # registers /wa + runs idempotent wa_ migrations
   ```
   `DATABASE_URL` here should be Supabase's **transaction pooler** string (port
   **6543**) so many short-lived connections multiplex through pgbouncer — the right
   choice for a scaled, bursty workload.

2. **Health endpoint for keep-warm** — add `GET /wa/healthz` → `200 "ok"` to
   `whatsapp_bot/webhooks.py` (no DB hit, so the pinger can't exhaust the pool).

3. **Slim `requirements-wa.txt`** (faster cold starts; verified sufficient):
   `Flask, Flask-SQLAlchemy, twilio, requests, psycopg2-binary, python-dotenv,
   gunicorn` (pin to the versions in `requirements.txt`).

4. **New Render web service** (dashboard, same repo + branch `main`):
   - Build: `pip install -r requirements-wa.txt`
   - Start: `gunicorn --worker-class gthread --workers 1 --threads 4 --timeout 30 wa_wsgi:app`
     (gthread = right for I/O-bound; the existing `Procfile` keeps serving the main
     `app:app` service; an explicit Start Command overrides the Procfile here.)

5. **Env vars on the new service** (copy from the current one): `TWILIO_AUTH_TOKEN`,
   `TWILIO_ACCOUNT_SID`, `TWILIO_MESSAGING_SERVICE_SID`, `TWILIO_WHATSAPP_FROM` (if
   used), all `WA_CT_*` template SIDs, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
   `SUPABASE_RESUME_BUCKET`, `BREVO_API_KEY`, `WA_FROM_EMAIL`, `WA_OPS_EMAIL`,
   `WA_IDLE_RESET_MINUTES`, the `DATABASE_URL` (pooler), and **critically**
   `TWILIO_WEBHOOK_URL = https://<new-service>.onrender.com/wa/webhook` (signature
   validation is pinned to it — wrong value → every request 403s).

6. **Keep-warm pinger** — a free external cron (cron-job.org / UptimeRobot) hits
   `/wa/healthz` every ~10 min so the instance never cold-starts on a real message.

7. **Repoint Twilio** — set the sandbox and/or production sender "When a message
   comes in" webhook to the new `…/wa/webhook` URL.

8. **Detach from the main site** (after verifying): remove the two bot lines from
   `app.py` (`from whatsapp_bot import init_app as init_wa_bot` + `init_wa_bot(app)`).
   Safe order: deploy new service → repoint Twilio → verify → then remove from
   `app.py`. Until that last step both URLs work, so there's no downtime.

## Phase 2 — Scale hardening for ~3k users

1. **Async message processing (the main scalability change)** in
   `whatsapp_bot/webhooks.py`: after the idempotency claim, hand the inbound to a
   module-level `concurrent.futures.ThreadPoolExecutor` (e.g. `max_workers=8`,
   configurable) and return the empty TwiML `200` immediately. The worker does
   `with app.app_context(): router.handle(inbound)` + the audit-row finalize.
   - Pass the real app via `current_app._get_current_object()`; Flask-SQLAlchemy's
     scoped session is thread-local, so each worker gets its own clean session.
   - Effect: the webhook returns in ~tens of ms regardless of how slow Supabase or
     Brevo are, and the résumé→upload→email path no longer ties up a request
     thread or risks Twilio's timeout.
2. **Tighten downstream HTTP timeouts** in `storage.py`/`emailer.py` (currently
   20–30 s) to ~8–10 s so a stuck dependency can't pin a worker for half a minute.
3. **Per-user rate limiting** (abuse + fairness on a public number): enforce the
   already-present `WA_RATE_LIMIT_PER_MIN` using a count over
   `wa_inbound_messages (from_phone, created_at)` (index already exists) — if over,
   skip processing and (optionally) send a gentle "slow down" once.
4. **Known limitation to note:** two messages from the *same* user within
   milliseconds could be processed by two threads concurrently (a state race).
   Rare for WhatsApp; mitigate later with a short per-phone lock if it ever bites.

## Free-tier specifics & limits (be honest about these)

- **Spin-down:** free web services sleep after 15 min idle and cold-start (~30–60 s)
  on the next hit. The keep-warm pinger (Phase 1.6) prevents real messages from
  cold-starting.
- **750 instance-hours/month, shared across all free services on the account.**
  Keeping the bot warm 24/7 ≈ ~730 h — fits *if it's the only always-warm free
  service*. If the **main Ofoodiez site is also a free service kept warm**, the two
  together blow past 750 h → throttling. Mitigation: keep only the bot warm, or put
  the user-facing bot on Render **Starter ($7/mo, always-on, 512 MB, no spin-down)**
  while the site stays free. (Strongly recommended for reliability at 3k users — but
  the architecture runs unchanged on free + pinger.)
- **0.1 shared CPU / 512 MB:** fine for this I/O-bound workload. Watch memory only
  on the résumé path (≤5 MB file + base64 in memory per submit); keep executor
  `max_workers` modest (≤8) so concurrent heavy ops stay well under 512 MB.
- **Scale-out path (no redesign):** because state is in Postgres and the webhook is
  idempotent, raising the instance count on a paid plan just works — the in-process
  ThreadPoolExecutor is per-instance and the idempotency key is shared in Postgres.

## Files to create / modify

- **Create** `wa_wsgi.py` (entry point) and `requirements-wa.txt` (slim deps).
- **Modify** `whatsapp_bot/webhooks.py`: add `/wa/healthz`; (Phase 2) async-dispatch
  via ThreadPoolExecutor.
- **Modify** `whatsapp_bot/storage.py` + `whatsapp_bot/emailer.py`: tighten timeouts
  (Phase 2).
- **Modify** `whatsapp_bot/router.py` or `webhooks.py`: enforce per-user rate limit
  (Phase 2).
- **Modify** `app.py`: remove the two `init_wa_bot` lines (Phase 1, step 8).
- **Optional:** fix the stale import in `run_wa_local.py:24`
  (`instagram_automation.database` → `database.models`) for local dev.
- **No changes** to the `whatsapp_bot/` flow logic, models, or `database/models.py`.

## Verification

1. **Local:** `./venv/bin/python -c "import wa_wsgi; print(wa_wsgi.app.url_map)"`
   shows `/wa/webhook` + `/wa/healthz` and nothing site-related loads.
2. **Boot on Render:** logs show `wa migrate: N applied, 0 failed` + clean gthread
   boot; `GET /wa/healthz` → 200; `POST /wa/webhook` (no signature) → 403.
3. **End-to-end from phone** (after Twilio repoint): new number → sign-up first;
   Employee (email + link) and Candidate (link-company + email-advocate) flows;
   advocate email arrives; rows land in the same Supabase.
4. **Async/latency:** confirm the webhook returns ~instantly (Render logs /
   Twilio debugger response time) even on a résumé submit, and the reply still
   arrives a moment later.
5. **Warm:** verify the pinger keeps the instance up (no cold-start gaps in logs),
   then re-test after removing the bot from `app.py`.
