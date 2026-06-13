"""Twilio WhatsApp webhook.

POST /wa/webhook is the single inbound endpoint. The flow (plan §3) is:

  1. Verify the X-Twilio-Signature against the PINNED webhook URL (fail closed).
  2. Claim the MessageSid: INSERT the audit row + COMMIT *before* any side
     effect. A duplicate SID raises IntegrityError -> we reply with empty TwiML
     (Twilio sends nothing) and do no reprocessing (idempotency).
  3. Route to the conversation state machine (whatsapp_bot.router), wrapped so a
     failure still leaves a debuggable audit row. Replies are sent via the Twilio
     REST API inside the router/messaging layer, not via TwiML (WhatsApp buttons
     require the Content API).
  4. Finalise the audit row (parsed_command, processing_ms, error) and COMMIT.
  5. Return an empty TwiML 200 ack (the reply already went out via REST).

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

from . import messaging, router, wa_bp
from .config import WaConfig
from .copy import ERROR
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

    # 3. Route to the conversation state machine. Replies are sent via REST
    #    inside the router; the webhook just acknowledges with empty TwiML.
    parsed_command = None
    error_text = None
    try:
        inbound = {
            "phone": from_phone,
            "profile_name": profile_name,
            "body": body,
            "button_payload": form.get("ButtonPayload"),
            "num_media": num_media,
            "media_url": form.get("MediaUrl0"),
            "media_content_type": form.get("MediaContentType0"),
        }
        parsed_command = router.handle(inbound)
    except Exception as exc:
        db.session.rollback()  # clear any aborted transaction so we can log + reply
        logger.exception("wa webhook: handler error for sid %s", message_sid)
        parsed_command = "error"
        error_text = str(exc)
        try:
            messaging.send_text(from_phone, ERROR["en"])
        except Exception:
            db.session.rollback()
            logger.exception("wa webhook: failed to send error reply")
    finally:
        audit.parsed_command = parsed_command
        audit.response_summary = (parsed_command or "")[:200]
        audit.processing_ms = int((time.monotonic() - started) * 1000)
        audit.error = error_text
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("wa webhook: failed to update audit row for sid %s", message_sid)

    return _twiml("")  # empty 200 ack; the reply already went out via REST
