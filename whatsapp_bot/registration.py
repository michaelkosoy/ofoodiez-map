"""Registration sub-flow (shared by the candidate & employee paths).

Collects first/last name + email as free text, shows a review with
Confirm/Edit/Restart buttons (the WA_CT_REGISTER_REVIEW Content template),
persists on Confirm, then hands off to the flow's main step (Phase C/E —
stubbed for now). Free-text prompts go out as plain messages; only the review
needs a Content template.
"""
import re
from datetime import datetime

from database.models import db

from . import conversation, copy, messaging
from .config import WaConfig

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def start(user, conv, flow):
    """Kick off registration for `flow` ('candidate' or 'employee')."""
    conversation.set_state(conv, flow, "reg_first_name", {})
    messaging.send_text(user.phone, copy.REG_FIRST_NAME)
    return "reg_start"


def handle(user, conv, payload, text):
    """Dispatch a message while the user is in a reg_* step."""
    step = conv.step
    data = dict(conv.data or {})

    if step == "reg_first_name":
        data["first_name"] = text
        conversation.set_state(conv, conv.flow, "reg_last_name", data)
        messaging.send_text(user.phone, copy.REG_LAST_NAME.format(first=text))
        return "reg_first_name"

    if step == "reg_last_name":
        data["last_name"] = text
        conversation.set_state(conv, conv.flow, "reg_email", data)
        messaging.send_text(user.phone, copy.REG_EMAIL.format(first=data.get("first_name", "")))
        return "reg_last_name"

    if step == "reg_email":
        if not _EMAIL_RE.match(text):
            messaging.send_text(user.phone, copy.REG_EMAIL_INVALID)
            return "reg_email_invalid"
        data["email"] = text
        conversation.set_state(conv, conv.flow, "reg_review", data)
        _send_review(user, data)
        return "reg_email"

    if step == "reg_review":
        if payload == "REG_CONFIRM":
            _persist(user, data)
            return enter_main(user, conv)
        if payload == "REG_EDIT":
            conversation.set_state(conv, conv.flow, "reg_first_name", {})
            messaging.send_text(user.phone, copy.REG_EDIT)
            return "reg_edit"
        # Any stray tap/text at the review: just re-show it.
        _send_review(user, data)
        return "reg_review"

    # Defensive: unknown step → restart registration cleanly.
    return start(user, conv, conv.flow)


def enter_main(user, conv):
    """Hand off to the flow's main step (Phase C/E — stubbed for now)."""
    if conv.flow == "employee":
        conversation.set_state(conv, "employee", "emp_main", {})
        messaging.send_text(user.phone, copy.REGISTERED_EMPLOYEE)
        return "registered_employee"
    conversation.set_state(conv, "candidate", "cand_main", {})
    messaging.send_text(user.phone, copy.REGISTERED_CANDIDATE)
    return "registered_candidate"


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
    user.terms_accepted_at = datetime.utcnow()
    db.session.commit()
