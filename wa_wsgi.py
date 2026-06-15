"""Standalone WSGI entry point — the WhatsApp bot only.

Run this as its own Render web service (`gunicorn wa_wsgi:app`) so the bot
deploys and scales independently of the main Ofoodiez site, while sharing the
same Supabase database. Mounts ONLY the `wa_bp` blueprint — no Telegram thread,
Google Maps, Instagram automation, or Admin routes load here.

Endpoints exposed:
  POST /wa/webhook   — Twilio WhatsApp inbound (signature-verified)
  GET  /wa/healthz   — bot health (blueprint-level)
  GET  /health       — service health (Render health check / keep-warm pinger)

See docs/whatsapp-bot-standalone-service-plan.md.
"""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify

from database.models import db
from whatsapp_bot import init_app as init_wa_bot

load_dotenv()

app = Flask(__name__)

# Same Supabase DB as the main site. Prefer the transaction-pooler URL (:6543)
# in the new service's env so bursty traffic multiplexes through pgbouncer.
_url = os.environ.get("DATABASE_URL") or os.environ.get("IG_DATABASE_URL")
if _url and _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _url or "sqlite:///wa_local.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Pool tuning only applies to real DBs (Postgres); SQLite's StaticPool rejects
# pool_size/max_overflow, so guard it for local/fallback runs.
_engine_opts = {"pool_pre_ping": True, "pool_recycle": 1800}
if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
    _engine_opts.update({"pool_size": 5, "max_overflow": 5})  # stay within Supabase pooler limits
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = _engine_opts

db.init_app(app)   # bind the shared db (wa_ tables already exist in Supabase)
init_wa_bot(app)   # register the /wa blueprint + run idempotent wa_ migrations


@app.route("/health")
def health():
    """Service health for Render's health check + the keep-warm pinger."""
    return jsonify(status="ok"), 200


if __name__ == "__main__":
    # Local dev: `python wa_wsgi.py` (gunicorn is used in production).
    app.run(port=int(os.environ.get("PORT", "5001")))
