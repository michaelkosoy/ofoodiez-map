"""Employee path: register as an advocate (someone who refers candidates).

Distinct from the candidate flow: collect the person's name, their company, and
one or more *work emails* (where candidate referrals are sent), then create an
advocate row per email. No job link / résumé — that's the candidate side.
On completion we return the user to the Welcome menu so a registered person can
freely jump between paths.
"""
import re
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from database.models import db

from . import conversation, copy, messaging
from .config import WaConfig
from .models import WaAdvocate, WaCompany

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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
        company_name = data.get("company_name", "your company")
        valid, had_personal = _parse_emails(text)
        if not valid:
            msg = copy.EMP_EMAIL_PERSONAL if had_personal else copy.EMP_EMAIL_INVALID
            messaging.send_prompt(user.phone, msg.format(company=company_name))
            return "emp_emails_invalid"
        saved = _create_advocates(user, data, valid)
        conversation.reset_state(conv)
        messaging.send_prompt(user.phone, copy.ADVOCATE_DONE.format(
            company=company_name, emails=", ".join(saved or valid)))
        _send_menu(user)
        return "advocate_created"

    # Unexpected step inside the employee flow → restart it cleanly.
    return start(user, conv)


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
