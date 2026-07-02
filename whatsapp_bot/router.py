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

    # Blocked users (flagged in the admin) are silently ignored — no reply.
    if user.is_blocked:
        logger.info("wa: ignoring message from blocked user %s", user.phone)
        return "blocked"

    # Idle timeout: a long-idle message starts fresh — sign-up if needed, else
    # the personalised Welcome.
    if _is_stale(conv):
        return _entry(user, conv)

    # Mid sign-up: finish it first. A registered phone never reaches here again.
    # Back-to-Menu / reset still escape, but just re-trigger sign-up while the
    # phone is still unregistered.
    if conv.flow == "registration":
        if payload == "BACK_TO_MENU" or text.lower() in RESET_WORDS:
            return _entry(user, conv)
        return registration.handle(user, conv, payload, text)

    # Hard reset always wins (Back-to-Menu / Restart buttons + reset words).
    if payload == "BACK_TO_MENU" or text.lower() in RESET_WORDS:
        return _entry(user, conv)

    # Path selection from the Welcome menu.
    if payload in _PATHS:
        return _enter_path(user, conv, _PATHS[payload])

    # In-flow dispatch.
    if conv.flow == "candidate" and conv.step and conv.step.startswith("cand_"):
        return candidate.handle(user, conv, inbound)
    if conv.flow == "employee" and conv.step and conv.step.startswith("emp_"):
        return employee.handle(user, conv, payload, text)

    # No active flow / anything unrecognized → sign-up (if needed) or Welcome.
    return _entry(user, conv)


def _entry(user, conv):
    """The single front door — everyone lands on the Welcome + route menu.
    Sign-up now happens only once a route (candidate/employee) is chosen."""
    return _welcome(user, conv)


def _enter_path(user, conv, flow):
    # Contact info needs no account.
    if flow == "contact":
        messaging.send_prompt(user.phone, copy.CONTACT_INFO)
        conversation.reset_state(conv)
        return "enter_contact"
    # Employees collect their identity inside the advocate flow's combined
    # question, so they skip the separate sign-up.
    if flow == "employee":
        return employee.start(user, conv)
    # Candidates sign up first (remembering the route), then resume into it.
    if not user.is_registered:
        return registration.start(user, conv, pending_flow="candidate")
    return candidate.start(user, conv)


def _welcome(user, conv):
    conversation.reset_state(conv)
    if user.is_registered:
        name = _display_name(user)
        messaging.send_text(user.phone, copy.WELCOME_BACK.format(
            name=f", {name}" if name else ""))
    else:
        messaging.send_text(user.phone, copy.WELCOME_INTRO)
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
