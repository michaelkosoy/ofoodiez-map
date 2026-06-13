"""User identity + per-user conversation state (DB-backed state machine store)."""
from datetime import datetime

from instagram_automation.database import db

from .models import WaConversation, WaUser


def get_or_create_user(phone, profile_name=None):
    user = WaUser.query.filter_by(phone=phone).first()
    if user is None:
        user = WaUser(phone=phone, profile_name=profile_name)
        db.session.add(user)
        db.session.commit()
    elif profile_name and user.profile_name != profile_name:
        user.profile_name = profile_name
        db.session.commit()
    return user


def get_state(user):
    conv = WaConversation.query.filter_by(user_id=user.id).first()
    if conv is None:
        conv = WaConversation(user_id=user.id, flow=None, step=None, data={})
        db.session.add(conv)
        db.session.commit()
    return conv


def set_state(conv, flow, step, data=None):
    conv.flow = flow
    conv.step = step
    if data is not None:
        conv.data = data  # whole-dict reassignment; JSON in-place mutation isn't tracked
    conv.updated_at = datetime.utcnow()
    db.session.commit()


def reset_state(conv):
    set_state(conv, None, None, {})
