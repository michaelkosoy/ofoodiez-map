"""Dispatch, Welcome menu, and path routing.

- Candidate: register (name + email + review) → company search → role → job link
  → résumé → submit.
- Employee: advocate registration (name → company → company email → confirm).
- Contact Us: returns contact info.
Text prompts carry a Back-to-Menu button (see messaging.send_prompt).
"""
import logging
from datetime import datetime, timedelta, timezone

from . import candidate, contact, conversation, copy, employee, messaging, profile, registration
from .config import WaConfig

logger = logging.getLogger("whatsapp_bot")

# Words that always reset to the Welcome menu. Kept minimal so they don't eat
# valid free-text answers (like a first name).
RESET_WORDS = {"menu", "restart"}

_PATHS = {
    "PATH_CANDIDATE": "candidate",
    "PATH_EMPLOYEE": "employee",
    "PATH_CONTACT": "contact",
    "PATH_PROFILE": "profile",  # "Edit my details" button on WA_CT_WELCOME_BACK
}

# Typed equivalents of the Welcome buttons. Some WhatsApp clients silently drop a
# quick-reply tap, so we accept the plain word too — but only when NOT mid-flow,
# so it can't swallow a company name / role answer.
PATH_WORDS = {
    "candidate": "candidate", "employee": "employee", "advocate": "employee",
    "contact": "contact", "contact us": "contact",
}

# Registered users can jump to their profile editor by keyword (the Welcome
# "Contact" button routes there too); multi-word so it won't eat a company name.
PROFILE_WORDS = {
    "my details", "my info", "my profile", "edit profile", "edit my details",
    "edit my info", "edit info", "update my details", "update my info",
}


def _wants_menu(payload, text):
    """The Back-to-Menu button + the reset keywords. We also match the button's
    visible label, not just payload BACK_TO_MENU: a tapped WA_CT_PROMPT button
    arrives with its label as the body (e.g. '↩️ Back to Menu') and its payload id
    isn't guaranteed to be BACK_TO_MENU across templates, so the label match is
    what makes the button reliably reset."""
    t = (text or "").strip().lower()
    return payload == "BACK_TO_MENU" or "back to menu" in t or t in RESET_WORDS


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
        if _wants_menu(payload, text):
            return _entry(user, conv)
        return registration.handle(user, conv, payload, text)

    # Hard reset always wins (Back-to-Menu / Restart buttons + reset words).
    if _wants_menu(payload, text):
        return _entry(user, conv)

    # Editing your own details is a later feature — point them to Contact Us.
    if user.is_registered and text.lower() in PROFILE_WORDS:
        return _profile_coming_soon(user, conv)

    # Path selection from the Welcome menu.
    if payload in _PATHS:
        return _enter_path(user, conv, _PATHS[payload])

    # Typed equivalent of a Welcome button (for clients that drop the tap — e.g.
    # WhatsApp Web/Desktop never sends quick-reply taps). Only at the menu (no
    # active flow) so it can't eat a mid-flow answer.
    if not conv.flow and text.lower() in PATH_WORDS:
        return _enter_path(user, conv, PATH_WORDS[text.lower()])

    # In-flow dispatch.
    if conv.flow == "candidate" and conv.step and conv.step.startswith("cand_"):
        return candidate.handle(user, conv, inbound)
    if conv.flow == "employee" and conv.step and conv.step.startswith("emp_"):
        return employee.handle(user, conv, payload, text)
    if conv.flow == "contact" and conv.step and conv.step.startswith("contact_"):
        return contact.handle(user, conv, payload, text)
    if conv.flow == "profile" and conv.step and conv.step.startswith("prof_"):
        return profile.handle(user, conv, payload, text)  # dormant — editing deferred

    # No active flow / anything unrecognized → sign-up (if needed) or Welcome.
    return _entry(user, conv)


def _entry(user, conv):
    """The single front door — everyone lands on the Welcome + route menu.
    Sign-up now happens only once a route (candidate/employee) is chosen."""
    return _welcome(user, conv)


def _enter_path(user, conv, flow):
    # "Edit my details" button — profile editing is deferred; show a coming-soon note.
    if flow == "profile":
        return _profile_coming_soon(user, conv)
    # Contact Us → let everyone send us a message (forwarded to ops by email).
    if flow == "contact":
        return contact.start(user, conv)
    # Employees collect their identity inside the advocate flow's combined
    # question, so they skip the separate sign-up.
    if flow == "employee":
        return employee.start(user, conv)
    # Candidates sign up first (remembering the route), then resume into it.
    if not user.is_registered:
        return registration.start(user, conv, pending_flow="candidate")
    return candidate.start(user, conv)


def _profile_coming_soon(user, conv):
    """Editing your own details is a later feature; for now nudge to Contact Us."""
    conversation.reset_state(conv)
    messaging.send_prompt(user.phone, copy.PROFILE_COMING_SOON)
    return "profile_coming_soon"


def _welcome(user, conv):
    conversation.reset_state(conv)
    name = _display_name(user)
    # Registered users get their own menu template when configured: greets by
    # name ({{1}}) and carries the "Edit my details" button (PATH_PROFILE).
    if user.is_registered and WaConfig.WA_CT_WELCOME_BACK:
        messaging.send_buttons(user.phone, WaConfig.WA_CT_WELCOME_BACK, {"1": name or "there"})
    elif WaConfig.WA_CT_WELCOME:
        # Shared template — greet returning users by name first (a second
        # "welcome" on top of the template's is fine; requested).
        if user.is_registered and name:
            messaging.send_text(user.phone, copy.WELCOME_HI.format(name=name))
        messaging.send_buttons(user.phone, WaConfig.WA_CT_WELCOME)
    elif user.is_registered:
        messaging.send_text(user.phone, copy.WELCOME_BACK.format(name=f", {name}" if name else ""))
    else:
        messaging.send_text(user.phone, copy.WELCOME_INTRO)
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
