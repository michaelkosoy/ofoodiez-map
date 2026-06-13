"""PR1/Task6: the signed, idempotent, audited webhook wired to the router.

Covers:
  - valid signature -> 200 empty TwiML ack; actual reply sent via REST
  - tampered signature -> 403
  - missing TWILIO_AUTH_TOKEN -> 403 (fail-closed)
  - duplicate MessageSid -> empty TwiML + exactly one audit row + reply sent once
  - audit row populated (incl. processing_ms, parsed_command == "welcome")
  - button payload routes correctly to enter_candidate
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


def test_valid_signed_message_acks_and_sends_welcome(client, app, sign, mock_twilio):
    params = _msg(Body="hi")
    resp = client.post("/wa/webhook", data=params, headers=sign(params))
    assert resp.status_code == 200
    assert "<Message>" not in resp.get_data(as_text=True)   # empty TwiML ack
    assert mock_twilio[0]["content_sid"] == "HX_welcome"    # welcome sent via REST


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


def test_duplicate_message_sid_is_processed_once(client, app, sign, mock_twilio):
    sid = "SMdup0000000000000000000000000001"
    params = _msg(MessageSid=sid, Body="hi")
    first = client.post("/wa/webhook", data=params, headers=sign(params))
    second = client.post("/wa/webhook", data=params, headers=sign(params))
    assert first.status_code == 200
    assert second.status_code == 200
    assert "<Message>" not in first.get_data(as_text=True)    # empty TwiML ack
    assert "<Message>" not in second.get_data(as_text=True)
    with app.app_context():
        rows = WaInboundMessage.query.filter_by(message_sid=sid).all()
        assert len(rows) == 1
    assert len(mock_twilio) == 1   # routed (welcome sent) once; duplicate not reprocessed


def test_button_payload_is_routed(client, app, sign, mock_twilio):
    sid = "SMbtn0000000000000000000000000001"
    params = _msg(MessageSid=sid, Body="")
    params["ButtonPayload"] = "PATH_CANDIDATE"
    resp = client.post("/wa/webhook", data=params, headers=sign(params))
    assert resp.status_code == 200
    with app.app_context():
        row = WaInboundMessage.query.filter_by(message_sid=sid).one()
        assert row.parsed_command == "enter_candidate"


def test_audit_row_is_populated(client, app, sign, mock_twilio):
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
        assert row.parsed_command == "welcome"
        assert row.processing_ms is not None
        assert row.processing_ms >= 0
