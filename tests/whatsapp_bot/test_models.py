from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from instagram_automation.database import db
from whatsapp_bot.models import WaUser, WaConversation, WaOutboundMessage


def test_user_has_registration_fields(app):
    with app.app_context():
        u = WaUser(phone="+972500000001", profile_name="Ada",
                   first_name="Ada", last_name="Lovelace",
                   email="ada@example.com", terms_accepted_at=datetime.utcnow())
        db.session.add(u); db.session.commit()
        got = WaUser.query.filter_by(phone="+972500000001").one()
        assert got.first_name == "Ada"
        assert got.email == "ada@example.com"
        assert got.terms_accepted_at is not None


def test_conversation_is_one_per_user(app):
    with app.app_context():
        u = WaUser(phone="+972500000002"); db.session.add(u); db.session.commit()
        c = WaConversation(user_id=u.id, flow="candidate", step="start", data={"x": 1})
        db.session.add(c); db.session.commit()
        got = WaConversation.query.filter_by(user_id=u.id).one()
        assert got.flow == "candidate"
        assert got.data == {"x": 1}


def test_outbound_message_row(app):
    with app.app_context():
        o = WaOutboundMessage(to_phone="+972500000003", body="hi",
                              twilio_sid="SM123", status="queued")
        db.session.add(o); db.session.commit()
        assert WaOutboundMessage.query.count() == 1


def test_referral_link_model_removed():
    import whatsapp_bot.models as m
    assert not hasattr(m, "WaReferralLink")


def test_is_registered_is_a_property(app):
    with app.app_context():
        full = WaUser(phone="+972500000005", first_name="Ada", email="ada@example.com")
        empty = WaUser(phone="+972500000006")
        assert full.is_registered is True   # property access, no parens
        assert empty.is_registered is False


def test_conversation_unique_per_user(app):
    with app.app_context():
        u = WaUser(phone="+972500000007"); db.session.add(u); db.session.commit()
        db.session.add(WaConversation(user_id=u.id, flow="candidate", step="a"))
        db.session.commit()
        db.session.add(WaConversation(user_id=u.id, flow="employee", step="b"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
