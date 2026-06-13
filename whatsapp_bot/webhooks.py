"""Twilio WhatsApp webhook.

POST /wa/webhook is the single inbound endpoint. The flow (plan §3) is:

  1. Verify the X-Twilio-Signature against the PINNED webhook URL (fail closed).
  2. Claim the MessageSid: INSERT the audit row + COMMIT *before* any side
     effect. A duplicate SID raises IntegrityError -> we reply with empty TwiML
     (Twilio sends nothing) and do no reprocessing (idempotency).
  3. Handle the message (PR1: a static bilingual help reply), wrapped so a
     failure still leaves a debuggable audit row.
  4. Finalise the audit row (parsed_command, response_summary, processing_ms,
     error) and COMMIT.
  5. Reply with TwiML.

Inbound webhooks are at-most-once (Twilio does not redeliver), so the
idempotency claim is cheap insurance rather than the main reliability
mechanism — but it makes the "handler finished, Twilio timed out, user retries"
case safe.
"""
import logging
import time

from flask import Response, request
from sqlalchemy.exc import IntegrityError
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from instagram_automation.database import db

from . import wa_bp
from .config import WaConfig
from .copy import ERROR, HELP
from .models import WaInboundMessage

logger = logging.getLogger("whatsapp_bot")


def _strip_whatsapp_prefix(value):
    """Twilio sends `From`/`To` as e.g. 'whatsapp:+9725...'; store bare E.164."""
    value = value or ""
    prefix = "whatsapp:"
    return value[len(prefix):] if value.startswith(prefix) else value


def _verify_twilio_signature(req):
    """Validate the inbound signature against the PINNED webhook URL.

    We pass WaConfig.TWILIO_WEBHOOK_URL (not request.url) because there is no
    ProxyFix and Render/Cloudflare rewrite the scheme/host, which would break
    HMAC validation. Fails closed if no auth token is configured.
    """
    token = WaConfig.TWILIO_AUTH_TOKEN
    if not token:
        return False
    validator = RequestValidator(token)
    signature = req.headers.get("X-Twilio-Signature", "")
    return validator.validate(WaConfig.TWILIO_WEBHOOK_URL, req.form.to_dict(), signature)


def _twiml(text):
    """Build a TwiML response. Empty text -> no <Message> -> Twilio stays silent."""
    resp = MessagingResponse()
    if text:
        resp.message(text)
    return Response(str(resp), mimetype="application/xml")


@wa_bp.route("/webhook", methods=["POST"])
def webhook():
    started = time.monotonic()

    # 1. Verify signature (fail closed) before doing anything else.
    if not _verify_twilio_signature(request):
        logger.warning("wa webhook: rejected request with invalid Twilio signature")
        return Response("Forbidden", status=403)

    form = request.form
    message_sid = form.get("MessageSid", "")
    from_phone = _strip_whatsapp_prefix(form.get("From", ""))
    profile_name = form.get("ProfileName")
    body = form.get("Body", "") or ""
    try:
        num_media = int(form.get("NumMedia", "0") or "0")
    except (TypeError, ValueError):
        num_media = 0

    # 2. Claim the MessageSid + record the audit row, BEFORE any side effect.
    #    A duplicate delivery loses the unique race and is answered silently.
    audit = WaInboundMessage(
        message_sid=message_sid,
        from_phone=from_phone,
        profile_name=profile_name,
        body=body,
        num_media=num_media,
    )
    db.session.add(audit)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        logger.info("wa webhook: duplicate MessageSid %s — skipping", message_sid)
        return _twiml("")  # already handled on the first delivery; stay silent

    # 3. Handle the message. PR1 replies with the static (English) help message;
    #    per-message language detection arrives with PR2's parser. copy.py
    #    already ships the Hebrew strings. We still wrap the handler so an
    #    unexpected failure leaves a debuggable audit row.
    reply = ""
    parsed_command = None
    error_text = None
    try:
        reply = HELP["en"]
        parsed_command = "help"
    except Exception as exc:  # defensive: keep the webhook a fast, safe 200
        logger.exception("wa webhook: handler error for sid %s", message_sid)
        reply = ERROR["en"]
        parsed_command = "error"
        error_text = str(exc)
    finally:
        # 4. Finalise the audit row regardless of success/failure.
        audit.parsed_command = parsed_command
        audit.response_summary = (reply or "")[:200]
        audit.processing_ms = int((time.monotonic() - started) * 1000)
        audit.error = error_text
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("wa webhook: failed to update audit row for sid %s", message_sid)

    # 5. Reply with TwiML.
    return _twiml(reply)
