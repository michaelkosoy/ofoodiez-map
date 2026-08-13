"""WhatsApp Referral-Link Bot.

A Twilio WhatsApp bot that lets users search approved job-referral links by
company and submit new links (held for human moderation). It mirrors the
`instagram_automation` blueprint pattern and reuses the single shared
SQLAlchemy `db` instance.

See docs/whatsapp-referral-bot-plan.md for the full design.
"""
import logging

from flask import Blueprint

wa_bp = Blueprint("whatsapp_bot", __name__, url_prefix="/wa")


def init_app(app):
    """Register the WhatsApp bot blueprint with the Flask app.

    Importing the submodules registers the models on the SHARED db metadata
    and attaches the webhook routes to ``wa_bp``. This intentionally does NOT
    call ``db.init_app`` (already done by instagram_automation.init_app). It runs
    idempotent, self-healing migrations (whatsapp_bot.migrate) so the live schema
    tracks the models without a manual SQL step — schema.sql remains the human
    reference (and still holds the optional Part 2 RLS for the site tables).

    Must be called AFTER ``instagram_automation.init_app`` so the shared db is
    initialized first.
    """
    from . import approvals, backfill, models, webhooks  # noqa: F401  (import for side effects)
    from .migrate import run_migrations

    app.register_blueprint(wa_bp)
    try:
        run_migrations(app)
    except Exception:  # never let a migration issue block app startup
        logging.getLogger("whatsapp_bot").exception("wa migrate: run_migrations failed")

    # Startup visibility: surface whether the RUNNING process actually sees the
    # email/storage config, so a missing env var isn't an invisible no-op.
    from .config import WaConfig
    logging.getLogger("whatsapp_bot").info(
        "wa: startup — Brevo email configured=%s (from=%s) · Supabase storage=%s",
        bool(WaConfig.BREVO_API_KEY and WaConfig.WA_FROM_EMAIL),
        WaConfig.WA_FROM_EMAIL or "(unset)",
        bool(WaConfig.SUPABASE_URL and WaConfig.SUPABASE_SERVICE_ROLE_KEY),
    )
    return app
