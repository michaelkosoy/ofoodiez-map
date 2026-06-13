"""Employee path: register as an advocate (someone who refers candidates).

Distinct from the candidate flow: collect the person's name, their company, and
one or more *work emails* (where candidate referrals are sent), then create an
advocate row per email. No job link / résumé — that's the candidate side.
On completion we return the user to the Welcome menu so a registered person can
freely jump between paths.
"""
import logging
import re
from datetime import datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database.models import db

from . import conversation, copy, messaging
from .config import WaConfig
from .models import WaAdvocate, WaCompany

logger = logging.getLogger("whatsapp_bot")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_CONFIRM_WORDS = {
    "yes", "y", "yep", "yeah", "yup", "ya", "ok", "okay", "k", "confirm",
    "confirmed", "correct", "sure", "👍", "✅",
}

# Consumer mailbox providers — an advocate must use a work email so referrals
# land in the right inbox and we can loosely tie them to the company.
_PERSONAL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "ymail.com",
    "hotmail.com", "hotmail.co.uk", "outlook.com", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com", "aol.com", "proton.me",
    "protonmail.com", "gmx.com", "yandex.com", "mail.com", "zoho.com",
}


def _normalize(name):
    return " ".join((name or "").strip().lower().split())


def get_or_create_company(name):
    norm = _normalize(name)
    company = WaCompany.query.filter_by(normalized_name=norm).first()
    if company:
        return company
    company = WaCompany(name=(name or "").strip(), normalized_name=norm)
    db.session.add(company)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        company = WaCompany.query.filter_by(normalized_name=norm).first()
    return company


def start(user, conv):
    # Returning users (already named) skip straight to their company.
    if user.is_registered:
        conversation.set_state(conv, "employee", "emp_company", {})
        messaging.send_prompt(user.phone, copy.EMP_COMPANY)
    else:
        conversation.set_state(conv, "employee", "emp_first_name", {})
        messaging.send_prompt(user.phone, copy.EMP_FIRST_NAME)
    return "emp_start"


def handle(user, conv, payload, text):
    step = conv.step
    data = dict(conv.data or {})

    if step == "emp_first_name":
        data["first_name"] = text
        conversation.set_state(conv, "employee", "emp_last_name", data)
        messaging.send_prompt(user.phone, copy.EMP_LAST_NAME.format(first=text))
        return "emp_first_name"

    if step == "emp_last_name":
        data["last_name"] = text
        user.first_name = data.get("first_name")
        user.last_name = text
        user.terms_accepted_at = user.terms_accepted_at or datetime.utcnow()
        db.session.commit()
        conversation.set_state(conv, "employee", "emp_company", data)
        messaging.send_prompt(user.phone, copy.EMP_COMPANY)
        return "emp_last_name"

    if step == "emp_company":
        company = get_or_create_company(text)
        data["company_id"] = company.id
        data["company_name"] = company.name
        conversation.set_state(conv, "employee", "emp_emails", data)
        messaging.send_prompt(user.phone, copy.EMP_EMAIL.format(company=company.name))
        return "emp_company"

    if step == "emp_emails":
        return _collect_emails(user, conv, data, text)

    if step == "emp_emails_confirm":
        if _is_confirm(text, payload):
            return _finalize(user, conv, data)
        # Anything that isn't a yes → treat it as a correction (new emails).
        return _collect_emails(user, conv, data, text)

    # Unexpected step inside the employee flow → restart it cleanly.
    return start(user, conv)


def _collect_emails(user, conv, data, text):
    """Parse the work email(s), then echo them back for a yes/no confirm."""
    company_name = data.get("company_name", "your company")
    valid, had_personal = _parse_emails(text)
    if not valid:
        msg = copy.EMP_EMAIL_PERSONAL if had_personal else copy.EMP_EMAIL_INVALID
        messaging.send_prompt(user.phone, msg.format(company=company_name))
        return "emp_emails_invalid"
    data["emails"] = valid
    conversation.set_state(conv, "employee", "emp_emails_confirm", data)
    messaging.send_prompt(user.phone, copy.EMP_EMAILS_CONFIRM.format(
        company=company_name, emails=", ".join(valid)))
    return "emp_emails_collected"


def _is_confirm(text, payload):
    if payload in ("EMP_CONFIRM", "EMP_EMAILS_CONFIRM"):
        return True
    return (text or "").strip().lower() in _CONFIRM_WORDS


def _finalize(user, conv, data):
    """Persist the advocate rows. On any DB error, never show a hiccup — roll
    back and re-ask for the email so the user can simply try again."""
    company_name = data.get("company_name", "your company")
    emails = data.get("emails") or []
    try:
        saved = _create_advocates(user, data, emails)
    except SQLAlchemyError:
        logger.exception("wa: failed to save advocate(s) for user %s", user.id)
        db.session.rollback()
        conversation.set_state(conv, "employee", "emp_emails", data)
        messaging.send_prompt(user.phone, copy.EMP_SAVE_FAILED.format(company=company_name))
        return "emp_save_failed"
    conversation.reset_state(conv)
    messaging.send_prompt(user.phone, copy.ADVOCATE_DONE.format(
        company=company_name, emails=", ".join(saved or emails)))
    _send_menu(user)
    return "advocate_created"


def _send_menu(user):
    """Drop the user back on the Welcome menu so they can pick any path next."""
    if WaConfig.WA_CT_WELCOME:
        messaging.send_buttons(user.phone, WaConfig.WA_CT_WELCOME)


def _parse_emails(text):
    """Split free text into deduped, lowercased work emails.

    Returns (valid_emails, had_personal_only): had_personal_only is True when the
    only thing we recognised was a personal-mailbox address, so we can nudge for
    a work email specifically.
    """
    valid, personal, seen = [], 0, set()
    for token in re.split(r"[,\s;]+", (text or "").strip()):
        token = token.strip().strip("<>").lower()
        if not token or not _EMAIL_RE.match(token):
            continue
        domain = token.rsplit("@", 1)[-1]
        if domain in _PERSONAL_DOMAINS:
            personal += 1
            continue
        if token not in seen:
            seen.add(token)
            valid.append(token)
    return valid, (personal > 0 and not valid)


def _create_advocates(user, data, emails):
    """Create/refresh one advocate row per work email. Returns the emails saved.

    Each (user, company, email) is its own row (see the unique index in
    schema.sql). If the pre-multi-email unique index is still in place, extra
    emails for the same company hit an IntegrityError and are skipped gracefully.
    """
    company_id = data.get("company_id")
    saved = []
    for email in emails:
        advocate = WaAdvocate.query.filter_by(
            user_id=user.id, company_id=company_id, email=email).first()
        if advocate:
            advocate.status = "active"
            advocate.updated_at = datetime.utcnow()
            db.session.commit()
            saved.append(email)
            continue
        db.session.add(WaAdvocate(
            user_id=user.id, company_id=company_id, email=email, status="active"))
        try:
            db.session.commit()
            saved.append(email)
        except IntegrityError:
            db.session.rollback()
    return saved
