"""One-time Terms-of-Use notice + consent stamping.

"Informed consent" is derived, never stored: terms_accepted_at > terms_notice_sent_at
(strict — the notice stamp always lands after sign-up's silent accepted stamp).
The notice only ever goes out reactively, right after an inbound message, so the
free-form fallback always lands inside WhatsApp's 24h session window.
"""
import logging
from datetime import datetime, timezone

from database.models import db

from . import copy, messaging
from .config import WaConfig

logger = logging.getLogger("whatsapp_bot")

AGREE_PAYLOAD = "TERMS_AGREE"
# Deliberately NOT "ok"/"yes" — those are flow confirm words (employee._CONFIRM_WORDS).
AGREE_WORDS = {"i agree", "agree", "מאשר", "מאשרת"}


def _norm(text):
    # A tapped quick-reply often arrives as its LABEL in Body ("I agree ✅").
    return (text or "").replace("✅", "").strip().lower()


def _naive(dt):
    # timestamptz is tz-aware from Postgres, naive from sqlite (router._is_stale pattern).
    if dt is not None and dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def intercept_agree(user, payload, text):
    """Always-on "I agree" catcher: stamp + short ack + swallow the message, so
    the button label never leaks into a pending free-text prompt (e.g. a company
    name). Returns a parsed_command string, or None to continue normal dispatch."""
    if payload != AGREE_PAYLOAD and _norm(text) not in AGREE_WORDS:
        return None
    user.terms_accepted_at = datetime.utcnow()
    db.session.commit()  # commit here: a downstream rollback must not undo consent
    messaging.send_text(user.phone, copy.TERMS_AGREED_ACK)
    return "terms_agree"


def on_message(user):
    """Router pre-hook (runs after intercept_agree, before dispatch — never
    blocks). Any message after a seen notice = consent; otherwise registered
    users who never got the notice get it now. The elif keeps the message that
    triggers the notice from also counting as consent for it."""
    accepted, notice = _naive(user.terms_accepted_at), _naive(user.terms_notice_sent_at)
    if notice is not None:
        if accepted is None or accepted < notice:
            user.terms_accepted_at = datetime.utcnow()
            db.session.commit()
    elif user.is_registered:
        send_notice(user)


def send_notice(user):
    """One-time ToU notice. Idempotent (no-op once stamped); on a send failure we
    don't stamp, so it simply retries on the user's next message."""
    if user.terms_notice_sent_at:
        return
    try:
        if WaConfig.WA_CT_TERMS:
            messaging.send_buttons(user.phone, WaConfig.WA_CT_TERMS, {"1": copy.TERMS_NOTICE})
        else:
            messaging.send_text(user.phone, copy.TERMS_NOTICE + "\n" + copy.TERMS_NOTICE_NO_BUTTON)
    except Exception:
        logger.exception("wa terms: notice send failed for %s", user.phone)
        return
    user.terms_notice_sent_at = datetime.utcnow()
    db.session.commit()
