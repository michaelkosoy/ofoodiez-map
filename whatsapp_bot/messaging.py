"""Outbound messaging — the only module that calls the Twilio REST API.

Replies are sent here (not via TwiML) because WhatsApp interactive buttons
require the Content API. Every send is logged to wa_outbound_messages.
"""
import json
import logging

from twilio.rest import Client

from instagram_automation.database import db

from .config import WaConfig
from .models import WaOutboundMessage

logger = logging.getLogger("whatsapp_bot")


def _client():
    return Client(WaConfig.TWILIO_ACCOUNT_SID, WaConfig.TWILIO_AUTH_TOKEN)


def _to(phone):
    return phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"


def _route_kwargs():
    """Choose the outbound sender: an explicit WhatsApp `from` number (the sandbox
    shared number, which can't belong to a Messaging Service) takes priority;
    otherwise route via the Messaging Service (the production sender)."""
    wa_from = WaConfig.TWILIO_WHATSAPP_FROM
    if wa_from:
        return {"from_": wa_from}
    return {"messaging_service_sid": WaConfig.TWILIO_MESSAGING_SERVICE_SID}


def _log(to_phone, twilio_sid=None, status=None, body=None, content_sid=None, error=None):
    row = WaOutboundMessage(
        to_phone=to_phone, body=body, content_sid=content_sid,
        twilio_sid=twilio_sid, status=status, error=error,
    )
    db.session.add(row)
    db.session.commit()


def send_text(to_phone, body):
    try:
        msg = _client().messages.create(
            to=_to(to_phone), body=body, **_route_kwargs(),
        )
        _log(to_phone, twilio_sid=msg.sid, status=getattr(msg, "status", None), body=body)
        return msg.sid
    except Exception as exc:
        logger.exception("wa send_text failed to %s", to_phone)
        _log(to_phone, body=body, error=str(exc))
        raise


def send_buttons(to_phone, content_sid, variables=None):
    try:
        msg = _client().messages.create(
            to=_to(to_phone), content_sid=content_sid,
            content_variables=json.dumps(variables or {}), **_route_kwargs(),
        )
        _log(to_phone, twilio_sid=msg.sid, status=getattr(msg, "status", None), content_sid=content_sid)
        return msg.sid
    except Exception as exc:
        logger.exception("wa send_buttons failed to %s", to_phone)
        _log(to_phone, content_sid=content_sid, error=str(exc))
        raise
