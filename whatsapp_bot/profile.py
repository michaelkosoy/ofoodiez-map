"""Signed-in user's self-service profile edit — name + email. (Their WhatsApp
number is their identity, so it isn't editable here.) Reached from the Welcome
menu's Contact option when the user is already registered, or by keyword."""
import re

from database.models import db

from . import conversation, copy, messaging

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def start(user, conv, prefix=""):
    conversation.set_state(conv, "profile", "prof_menu", {})
    _send_menu(user, prefix)
    return "prof_start"


def _send_menu(user, prefix=""):
    name = " ".join(x for x in (user.first_name, user.last_name) if x) or "—"
    messaging.send_prompt(user.phone, prefix + copy.PROFILE_MENU.format(
        name=name, email=user.email or "—"))


def handle(user, conv, payload, text):
    step = conv.step
    t = (text or "").strip()

    if step == "prof_menu":
        low = t.lower()
        if low in ("name", "1"):
            conversation.set_state(conv, "profile", "prof_name", {})
            messaging.send_prompt(user.phone, copy.PROFILE_NAME_PROMPT)
            return "prof_name"
        if low in ("email", "2"):
            conversation.set_state(conv, "profile", "prof_email", {})
            messaging.send_prompt(user.phone, copy.PROFILE_EMAIL_PROMPT)
            return "prof_email"
        _send_menu(user)  # unrecognized → re-show the menu
        return "prof_menu"

    if step == "prof_name":
        parts = t.split()
        if not parts:
            messaging.send_prompt(user.phone, copy.PROFILE_NAME_PROMPT)
            return "prof_name"
        user.first_name = parts[0]
        user.last_name = " ".join(parts[1:]) or None
        db.session.commit()
        return start(user, conv, prefix="✅ Name updated!\n\n")

    if step == "prof_email":
        if not _EMAIL_RE.match(t):
            messaging.send_prompt(user.phone, copy.PROFILE_EMAIL_INVALID)
            return "prof_email_invalid"
        user.email = t.lower()
        db.session.commit()
        return start(user, conv, prefix="✅ Email updated!\n\n")

    return start(user, conv)
