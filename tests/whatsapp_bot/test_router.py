from whatsapp_bot import router, conversation
from whatsapp_bot.models import WaConversation


def _inbound(**kw):
    base = {"phone": "+972500000030", "profile_name": "Alan", "body": "",
            "button_payload": None, "num_media": 0,
            "media_url": None, "media_content_type": None}
    base.update(kw)
    return base


def test_first_contact_sends_welcome(app, mock_twilio):
    with app.app_context():
        label = router.handle(_inbound(body="hi"))
        assert label == "welcome"
        assert mock_twilio[0]["content_sid"] == "HX_welcome"


def test_candidate_button_enters_candidate_flow(app, mock_twilio):
    with app.app_context():
        router.handle(_inbound(body="hi"))            # welcome first
        label = router.handle(_inbound(button_payload="PATH_CANDIDATE"))
        assert label == "enter_candidate"
        u = conversation.get_or_create_user("+972500000030")
        assert conversation.get_state(u).flow == "candidate"
        assert any("Candidate" in (c.get("body") or "") for c in mock_twilio)


def test_back_to_menu_resets(app, mock_twilio):
    with app.app_context():
        router.handle(_inbound(body="hi"))
        router.handle(_inbound(button_payload="PATH_EMPLOYEE"))
        label = router.handle(_inbound(button_payload="BACK_TO_MENU"))
        assert label == "welcome"
        u = conversation.get_or_create_user("+972500000030")
        assert conversation.get_state(u).flow is None
