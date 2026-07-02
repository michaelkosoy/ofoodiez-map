"""One-time sign-up, shared by both paths.

Sign-up is the first thing an unregistered phone does (see router._entry). It's
its own conversation flow ("registration"): collect first/last name + email,
show a Confirm/Edit review (WA_CT_REGISTER_REVIEW), persist, then drop the user
on the Welcome menu. ``WaUser.is_registered`` (first_name AND email) then stays
true forever, so neither the candidate nor the employee path ever asks again.
"""
import re
from datetime import datetime

from database.models import db

from . import conversation, copy, messaging
from .config import WaConfig

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def start(user, conv, pending_flow=None):
    # pending_flow ("candidate"/"employee") is remembered so we resume into that
    # route once sign-up is confirmed, instead of bouncing back to the menu.
    conversation.set_state(conv, "registration", "reg_first_name",
                           {"pending_flow": pending_flow} if pending_flow else {})
    messaging.send_prompt(user.phone, copy.REG_FIRST_NAME)
    return "reg_start"


def handle(user, conv, payload, text):
    step = conv.step
    data = dict(conv.data or {})

    if step == "reg_first_name":
        data["first_name"] = text.strip()
        conversation.set_state(conv, "registration", "reg_last_name", data)
        messaging.send_prompt(user.phone, copy.REG_LAST_NAME.format(first=data["first_name"]))
        return "reg_first_name"

    if step == "reg_last_name":
        data["last_name"] = text.strip()
        conversation.set_state(conv, "registration", "reg_email", data)
        messaging.send_prompt(user.phone, copy.REG_EMAIL.format(first=data.get("first_name", "")))
        return "reg_last_name"

    if step == "reg_email":
        if not _EMAIL_RE.match(text.strip()):
            messaging.send_prompt(user.phone, copy.REG_EMAIL_INVALID)
            return "reg_email_invalid"
        data["email"] = text.strip()
        conversation.set_state(conv, "registration", "reg_review", data)
        _send_review(user, data)
        return "reg_email"

    if step == "reg_review":
        if payload == "REG_CONFIRM":
            _persist(user, data)
            # Resume into the route they picked before sign-up; else the menu.
            from . import router, candidate, employee  # late import (avoid cycle)
            pending = data.get("pending_flow")
            if pending == "candidate":
                return candidate.start(user, conv, returning=False)
            if pending == "employee":
                return employee.start(user, conv)
            return router._welcome(user, conv)
        if payload == "REG_EDIT":
            conversation.set_state(conv, "registration", "reg_first_name", {})
            messaging.send_prompt(user.phone, copy.REG_EDIT)
            return "reg_edit"
        _send_review(user, data)
        return "reg_review"

    return start(user, conv)


def _send_review(user, data):
    name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
    messaging.send_buttons(user.phone, WaConfig.WA_CT_REGISTER_REVIEW, {
        "1": name or "—",
        "2": user.phone,
        "3": data.get("email", "—"),
    })


def _persist(user, data):
    user.first_name = data.get("first_name")
    user.last_name = data.get("last_name")
    user.email = data.get("email")
    user.terms_accepted_at = user.terms_accepted_at or datetime.utcnow()
    db.session.commit()
