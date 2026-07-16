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
import json
import logging
import time

from flask import Response, request
from sqlalchemy.exc import IntegrityError
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from database.models import db

from . import messaging, router, wa_bp
from .config import WaConfig
from .copy import ERROR
from .models import WaInboundMessage, WaOutboundMessage

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


@wa_bp.route("/healthz", methods=["GET"])
def healthz():
    """Lightweight liveness check (no DB hit) for keep-warm pingers / monitors."""
    return Response("ok", mimetype="text/plain")


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
        logger.warning("wa webhook: duplicate MessageSid %s — skipping", message_sid)
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
        # ponytail: temp diagnostic at WARNING so it surfaces (app logs default to
        # WARNING). The audit table doesn't store the button payload/text; log them
        # to pin down button-tap routing. Remove once done.
        logger.warning("wa webhook in: sid=%s from=%s payload=%r btntext=%r body=%r",
                       message_sid, from_phone, form.get("ButtonPayload"),
                       form.get("ButtonText"), body[:80])
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


@wa_bp.route("/debug/messages", methods=["GET"])
def debug_messages():
    """Diagnostics: the last few inbound/outbound audit rows. Send failures ack
    with a silent 200, so this is the fastest way to see WHY a reply didn't go
    out, without direct DB access. Keyed like the backfill endpoints."""
    from .backfill import _secret
    if request.args.get("key") != _secret():
        return Response("forbidden", status=403)
    inbound = [{
        "at": str(r.created_at), "from": r.from_phone, "body": (r.body or "")[:100],
        "command": r.parsed_command, "ms": r.processing_ms, "error": r.error,
    } for r in WaInboundMessage.query.order_by(WaInboundMessage.id.desc()).limit(8)]
    outbound = []
    client = None
    for r in WaOutboundMessage.query.order_by(WaOutboundMessage.id.desc()).limit(8):
        o = {"at": str(r.created_at), "to": r.to_phone, "sid": r.twilio_sid,
             "status": r.status, "error": r.error,
             "body": (r.body or r.content_sid or "")[:100]}
        if r.twilio_sid:  # final delivery verdict from Twilio (queued != delivered)
            try:
                client = client or messaging._client()
                m = client.messages(r.twilio_sid).fetch()
                o["live_status"] = m.status
                o["error_code"] = m.error_code
            except Exception as exc:
                o["live_status"] = f"fetch failed: {exc}"
        outbound.append(o)
    return Response(json.dumps({"inbound": inbound, "outbound": outbound},
                               ensure_ascii=False, indent=1),
                    mimetype="application/json")


@wa_bp.route("/debug/templates", methods=["GET"])
def debug_templates():
    """Diagnostics: every configured content template + its LIVE WhatsApp approval
    status from Twilio's Content API. An unapproved template fails sends with a
    silent async 63013, so this shows exactly which env var points at a bad SID."""
    from .backfill import _secret
    if request.args.get("key") != _secret():
        return Response("forbidden", status=403)
    import requests as _rq
    auth = (WaConfig.TWILIO_ACCOUNT_SID, WaConfig.TWILIO_AUTH_TOKEN)
    out = {}
    for name in ("WA_CT_WELCOME", "WA_CT_WELCOME_BACK", "WA_CT_BACK_TO_MENU",
                 "WA_CT_REGISTER_REVIEW", "WA_CT_PROMPT", "WA_CT_EMPLOYEE_CONFIRM",
                 "WA_CT_EMP_METHOD", "WA_CT_EXPLORE_MORE", "WA_CT_ADVOCATE_PING"):
        sid = getattr(WaConfig, name, None)
        if not sid:
            out[name] = None
            continue
        info = {"sid": sid}
        try:
            r = _rq.get(f"https://content.twilio.com/v1/Content/{sid}/ApprovalRequests",
                        auth=auth, timeout=10)
            wa = (r.json() or {}).get("whatsapp") or {}
            info["template_name"] = wa.get("name")
            info["approval_status"] = wa.get("status")
            if wa.get("rejection_reason"):
                info["rejection_reason"] = wa.get("rejection_reason")
            # the content definition itself (body + button count) — a structure
            # that violates WhatsApp rules fails sends with 63013 even in-session
            rc = _rq.get(f"https://content.twilio.com/v1/Content/{sid}",
                         auth=auth, timeout=10)
            types = (rc.json() or {}).get("types") or {}
            info["types"] = {
                t: {"body": str((d or {}).get("body"))[:90],
                    "buttons": [a.get("title") for a in (d or {}).get("actions") or []]}
                for t, d in types.items()
            }
        except Exception as exc:
            info["approval_status"] = f"fetch failed: {exc}"
        out[name] = info
    return Response(json.dumps(out, ensure_ascii=False, indent=1),
                    mimetype="application/json")
