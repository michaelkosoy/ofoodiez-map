from whatsapp_bot import conversation
from whatsapp_bot.models import WaUser, WaConversation


def test_get_or_create_user_is_idempotent(app):
    with app.app_context():
        u1 = conversation.get_or_create_user("+972500000020", "Grace")
        u2 = conversation.get_or_create_user("+972500000020", "Grace")
        assert u1.id == u2.id
        assert WaUser.query.filter_by(phone="+972500000020").count() == 1
        assert u1.profile_name == "Grace"


def test_state_lifecycle(app):
    with app.app_context():
        u = conversation.get_or_create_user("+972500000021")
        conv = conversation.get_state(u)
        assert conv.flow is None and conv.step is None
        conversation.set_state(conv, "candidate", "cand_company", {"company": "Intuit"})
        again = conversation.get_state(u)
        assert again.flow == "candidate"
        assert again.step == "cand_company"
        assert again.data == {"company": "Intuit"}
        conversation.reset_state(conv)
        assert conversation.get_state(u).flow is None
        assert WaConversation.query.filter_by(user_id=u.id).count() == 1
