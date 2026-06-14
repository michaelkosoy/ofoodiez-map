"""Dispatch, Welcome menu, and path routing.

- Candidate: register (name + email + review) → company search → role → job link
  → résumé → submit.
- Employee: advocate registration (name → company → company email → confirm).
- Contact Us: returns contact info.
Text prompts carry a Back-to-Menu button (see messaging.send_prompt).
"""
import logging
from datetime import datetime, timedelta, timezone

from . import candidate, conversation, copy, employee, messaging, registration
from .config import WaConfig

logger = logging.getLogger("whatsapp_bot")

# Words that always reset to the Welcome menu. Kept minimal so they don't eat
# valid free-text answers (like a first name).
RESET_WORDS = {"menu", "restart"}

_PATHS = {
    "PATH_CANDIDATE": "candidate",
    "PATH_EMPLOYEE": "employee",
    "PATH_CONTACT": "contact",
}


def handle(inbound):
    user = conversation.get_or_create_user(inbound["phone"], inbound.get("profile_name"))
    conv = conversation.get_state(user)
    payload = inbound.get("button_payload")
    text = (inbound.get("body") or "").strip()

    # Idle timeout: if it's been a while since the last activity, treat this
    # message as a brand-new conversation (fresh, personalised Welcome).
    if _is_stale(conv):
        return _welcome(user, conv)

    # Hard reset always wins (Back-to-Menu / Restart buttons + reset words).
    if payload == "BACK_TO_MENU" or text.lower() in RESET_WORDS:
        return _welcome(user, conv)

    # Path selection from the Welcome menu.
    if payload in _PATHS:
        return _enter_path(user, conv, _PATHS[payload])

    # In-flow dispatch.
    if conv.flow == "candidate":
        if conv.step and conv.step.startswith("reg_"):
            return registration.handle(user, conv, payload, text)
        if conv.step and conv.step.startswith("cand_"):
            return candidate.handle(user, conv, inbound)
        messaging.send_prompt(user.phone, copy.MAIN_COMING_SOON)
        return "main_coming_soon"

    if conv.flow == "employee":
        if conv.step and conv.step.startswith("emp_"):
            return employee.handle(user, conv, payload, text)
        messaging.send_prompt(user.phone, copy.MAIN_COMING_SOON)
        return "main_coming_soon"

    # No active flow / anything unrecognized → Welcome.
    return _welcome(user, conv)


def _enter_path(user, conv, flow):
    if flow == "contact":
        messaging.send_prompt(user.phone, copy.CONTACT_INFO)
        conversation.reset_state(conv)
        return "enter_contact"
    if flow == "employee":
        return employee.start(user, conv)
    # candidate
    if user.is_registered:
        return candidate.start(user, conv)
    return registration.start(user, conv, "candidate")


def _welcome(user, conv):
    conversation.reset_state(conv)
    name = _display_name(user)
    messaging.send_text(user.phone, copy.WELCOME_GREETING.format(
        name=f", {name}" if name else ""))
    messaging.send_buttons(user.phone, WaConfig.WA_CT_WELCOME)
    return "welcome"


def _display_name(user):
    """Best name to greet by: their registered first name, else the first token
    of their WhatsApp profile name, else nothing (we key users by phone)."""
    name = (user.first_name or "").strip()
    if not name:
        profile = (user.profile_name or "").strip()
        name = profile.split()[0] if profile else ""
    return name


def _is_stale(conv):
    """True when the last activity was over IDLE_RESET_MINUTES ago."""
    last = conv.updated_at
    if last is None:
        return False
    if last.tzinfo is not None:  # a timestamptz column can come back tz-aware
        last = last.astimezone(timezone.utc).replace(tzinfo=None)
    return datetime.utcnow() - last > timedelta(minutes=WaConfig.IDLE_RESET_MINUTES)
