"""PR1: the signed, idempotent, audited webhook (the "echo" bot).

Covers the plan's PR1 "Tests required":
  - valid signature -> 200 with <Message>
  - tampered signature -> 403
  - missing TWILIO_AUTH_TOKEN -> 403 (fail-closed)
  - duplicate MessageSid -> empty TwiML + exactly one audit row
  - audit row populated (incl. processing_ms)
"""
from whatsapp_bot.models import WaInboundMessage


def _msg(**overrides):
    """A representative Twilio inbound-WhatsApp form payload."""
    params = {
        "MessageSid": "SM00000000000000000000000000000001",
        "From": "whatsapp:+972546824120",
        "To": "whatsapp:+14155238886",
        "Body": "hello",
        "NumMedia": "0",
        "ProfileName": "Alice",
    }
    params.update(overrides)
    return params


def test_valid_signed_message_returns_200_with_message(client, sign):
    params = _msg(Body="hello")
    resp = client.post("/wa/webhook", data=params, headers=sign(params))

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<Message>" in body
    assert "Ofoodiez" in body  # the bilingual help reply


def test_tampered_signature_is_rejected_403(client, sign):
    params = _msg()
    headers = sign(params)  # sign the original params...
    params["Body"] = "tampered after signing"  # ...then change a field
    resp = client.post("/wa/webhook", data=params, headers=headers)

    assert resp.status_code == 403


def test_missing_auth_token_fails_closed_403(client, sign, monkeypatch):
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    params = _msg()
    resp = client.post("/wa/webhook", data=params, headers=sign(params))

    assert resp.status_code == 403


def test_duplicate_message_sid_is_processed_once(client, app, sign):
    sid = "SMdup0000000000000000000000000001"
    params = _msg(MessageSid=sid, Body="hello")

    first = client.post("/wa/webhook", data=params, headers=sign(params))
    second = client.post("/wa/webhook", data=params, headers=sign(params))

    assert first.status_code == 200
    assert second.status_code == 200
    assert "<Message>" in first.get_data(as_text=True)
    assert "<Message>" not in second.get_data(as_text=True)  # duplicate is silent

    with app.app_context():
        rows = WaInboundMessage.query.filter_by(message_sid=sid).all()
        assert len(rows) == 1


def test_audit_row_is_populated(client, app, sign):
    sid = "SMaudit000000000000000000000000001"
    params = _msg(
        MessageSid=sid,
        From="whatsapp:+972546824120",
        Body="hello",
        ProfileName="Bob Smith",
    )
    resp = client.post("/wa/webhook", data=params, headers=sign(params))
    assert resp.status_code == 200

    with app.app_context():
        row = WaInboundMessage.query.filter_by(message_sid=sid).first()
        assert row is not None
        assert row.from_phone == "+972546824120"  # 'whatsapp:' prefix stripped
        assert row.profile_name == "Bob Smith"
        assert row.body == "hello"
        assert row.num_media == 0
        assert row.parsed_command == "help"
        assert row.processing_ms is not None
        assert row.processing_ms >= 0
