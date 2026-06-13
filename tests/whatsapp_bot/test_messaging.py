import json
from whatsapp_bot import messaging
from whatsapp_bot.models import WaOutboundMessage


def test_send_text_calls_twilio_and_logs(app, mock_twilio):
    with app.app_context():
        sid = messaging.send_text("+972500000010", "hello there")
        assert sid.startswith("SM_fake_")
        call = mock_twilio[0]
        assert call["to"] == "whatsapp:+972500000010"
        assert call["body"] == "hello there"
        assert call["messaging_service_sid"] == "MG_test"
        row = WaOutboundMessage.query.one()
        assert row.body == "hello there"
        assert row.twilio_sid == sid


def test_send_buttons_uses_content_sid_and_variables(app, mock_twilio):
    with app.app_context():
        messaging.send_buttons("+972500000011", "HX_welcome", {"1": "Ofoodiez"})
        call = mock_twilio[0]
        assert call["content_sid"] == "HX_welcome"
        assert json.loads(call["content_variables"]) == {"1": "Ofoodiez"}
        assert WaOutboundMessage.query.one().content_sid == "HX_welcome"
