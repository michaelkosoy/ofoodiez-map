"""Dispatch + Welcome flow.

Phase A only routes the Welcome menu and Back-to-Menu. The three path
selections set the flow and reply with a transitional stub; Phases B-F replace
those stubs with the real registration/candidate/employee/contact handlers.
"""
import logging

from . import conversation, messaging
from .config import WaConfig

logger = logging.getLogger("whatsapp_bot")

# Transitional stubs (replaced in Phases B-F).
_PATH_STUBS = {
    "PATH_CANDIDATE": ("candidate", "You're in the Candidate flow! (coming soon)"),
    "PATH_EMPLOYEE": ("employee", "You're in the Employee flow! (coming soon)"),
    "PATH_CONTACT": ("contact", "You're in Contact Us! (coming soon)"),
}


def handle(inbound):
    user = conversation.get_or_create_user(inbound["phone"], inbound.get("profile_name"))
    conv = conversation.get_state(user)
    payload = inbound.get("button_payload")

    # PATH_* buttons start a new flow — handle BEFORE anything else so that tapping
    # a path right after the welcome menu (where flow=None) enters the flow instead
    # of re-showing the menu.
    if payload in _PATH_STUBS:
        flow, stub = _PATH_STUBS[payload]
        conversation.set_state(conv, flow, "start", {})
        messaging.send_text(user.phone, stub)
        return f"enter_{flow}"

    # Phase A: everything else (Back-to-Menu, reset words, mid-stub, unrecognized)
    # resets and re-shows the Welcome menu. Phase B inserts reset-keyword handling
    # and flow-aware dispatch here for users with an active flow.
    return _welcome(user, conv)


def _welcome(user, conv):
    conversation.reset_state(conv)
    messaging.send_buttons(user.phone, WaConfig.WA_CT_WELCOME)
    return "welcome"
