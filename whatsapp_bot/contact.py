"""Contact Us: collect a free-text message and email it to ops (best-effort).

Profile editing is deferred for now, so Contact Us is purely "send us a message":
the user types one message, we forward it to WA_OPS_EMAIL (reply-to their email
when we have one), then confirm.
"""
import logging

from database.models import db

from . import conversation, copy, emailer, messaging
from .models import WaContactMessage

logger = logging.getLogger("whatsapp_bot")


def start(user, conv):
    conversation.set_state(conv, "contact", "contact_msg", {})
    messaging.send_prompt(user.phone, copy.CONTACT_PROMPT)
    return "contact_start"


def handle(user, conv, payload, text):
    if conv.step == "contact_msg":
        msg = (text or "").strip()
        if not msg:                       # media-only / empty → re-ask
            messaging.send_prompt(user.phone, copy.CONTACT_PROMPT)
            return "contact_waiting"
        name = (f"{user.first_name or ''} {user.last_name or ''}".strip()
                or user.profile_name or "A user")
        try:
            emailer.send_contact_email(name, user.phone, user.email, msg)
        except Exception:                 # never break the flow on a send hiccup
            logger.exception("wa contact: send failed")
        try:                              # store for the admin "Contact us" tab
            db.session.add(WaContactMessage(
                user_id=user.id, name=name, phone=user.phone,
                email=user.email, message=msg,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("wa contact: store failed")
        conversation.reset_state(conv)
        messaging.send_prompt(user.phone, copy.CONTACT_SENT)
        return "contact_sent"
    return start(user, conv)
