"""WhatsApp Referral-Link Bot.

A Twilio WhatsApp bot that lets users search approved job-referral links by
company and submit new links (held for human moderation). It mirrors the
`instagram_automation` blueprint pattern and reuses the single shared
SQLAlchemy `db` instance.

See docs/whatsapp-referral-bot-plan.md for the full design.
"""
from flask import Blueprint

wa_bp = Blueprint("whatsapp_bot", __name__, url_prefix="/wa")


def init_app(app):
    """Register the WhatsApp bot blueprint with the Flask app.

    Importing the submodules registers the models on the SHARED db metadata
    and attaches the webhook routes to ``wa_bp``. This intentionally does NOT
    call ``db.init_app`` (already done by instagram_automation.init_app) nor
    ``db.create_all`` — the wa_ tables are created by the one-time Supabase SQL
    script (with RLS) described in docs/whatsapp-referral-bot-plan.md §4.

    Must be called AFTER ``instagram_automation.init_app`` so the shared db is
    initialized first.
    """
    from . import models, webhooks  # noqa: F401  (import for side effects)

    app.register_blueprint(wa_bp)
    return app
