"""Employee path: register as an advocate (someone who refers candidates).

After name + company, the advocate picks how they want to refer:
  • EMAIL  — they get a candidate's CV by email and refer them manually.
  • LINK   — they hand over a self-serve coded referral link, which the bot
             then auto-shares with any candidate who searches that company.
No job link / résumé here — that's the candidate side. On completion the flow
just resets (no auto Welcome); the user can type 'menu' to do more.
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
_URL_RE = re.compile(r"^https?://[^\s/]+\.[^\s/]+", re.IGNORECASE)

_CONFIRM_WORDS = {
    "yes", "y", "yep", "yeah", "yup", "ya", "ok", "okay", "k", "confirm",
    "confirmed", "correct", "sure", "👍", "✅",
}
_METHOD_EMAIL_WORDS = {"1", "email", "emails", "e", "mail", "notify"}
_METHOD_LINK_WORDS = {"2", "link", "links", "l", "code", "referral", "referral link"}
_SKIP_WORDS = {"skip", "pass", "no", "none", "n/a", "na", "-", "later"}

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
    # Sign-up already happened up front (router gates on is_registered), so the
    # advocate goes straight to picking their company.
    conversation.set_state(conv, "employee", "emp_company", {})
    messaging.send_prompt(user.phone, copy.EMP_COMPANY)
    return "emp_start"


def handle(user, conv, payload, text):
    step = conv.step
    data = dict(conv.data or {})

    if step == "emp_company":
        company = get_or_create_company(text)
        data["company_id"] = company.id
        data["company_name"] = company.name
        conversation.set_state(conv, "employee", "emp_title", data)
        messaging.send_prompt(user.phone, copy.EMP_TITLE.format(company=company.name))
        return "emp_company"

    if step == "emp_title":
        # Optional: their role at the company, used to match candidates by role.
        if (text or "").strip().lower() not in _SKIP_WORDS:
            data["role_title"] = (text or "").strip()
        conversation.set_state(conv, "employee", "emp_method", data)
        _send_method_choice(user, data.get("company_name", "your company"))
        return "emp_title"

    if step == "emp_method":
        choice = _method_choice(text, payload)
        company_name = data.get("company_name", "your company")
        if choice == "email":
            conversation.set_state(conv, "employee", "emp_emails", data)
            messaging.send_prompt(user.phone, copy.EMP_EMAIL.format(company=company_name))
            return "emp_method_email"
        if choice == "link":
            conversation.set_state(conv, "employee", "emp_link", data)
            messaging.send_prompt(user.phone, copy.EMP_LINK_PROMPT.format(company=company_name))
            return "emp_method_link"
        _send_method_choice(user, company_name)
        return "emp_method_reprompt"

    if step == "emp_link":
        return _save_link(user, conv, data, text)

    if step == "emp_emails":
        return _collect_emails(user, conv, data, text)

    if step == "emp_emails_confirm":
        if _is_confirm(text, payload):
            return _finalize(user, conv, data)
        # Anything that isn't a yes → treat it as a correction (new emails).
        return _collect_emails(user, conv, data, text)

    # Unexpected step inside the employee flow → restart it cleanly.
    return start(user, conv)


def _send_method_choice(user, company):
    """Ask how the advocate wants to refer. Uses a quick-reply button template if
    WA_CT_EMP_METHOD is configured, otherwise a plain 1/2 text prompt."""
    if WaConfig.WA_CT_EMP_METHOD:
        messaging.send_buttons(user.phone, WaConfig.WA_CT_EMP_METHOD)
    else:
        messaging.send_prompt(user.phone, copy.EMP_METHOD_PROMPT.format(company=company))


def _method_choice(text, payload):
    if payload == "EMP_METHOD_EMAIL":
        return "email"
    if payload == "EMP_METHOD_LINK":
        return "link"
    t = (text or "").strip().lower()
    if t in _METHOD_EMAIL_WORDS:
        return "email"
    if t in _METHOD_LINK_WORDS:
        return "link"
    return None


def _save_link(user, conv, data, text):
    """Validate + persist a self-serve referral link. Never hiccups on a DB
    error — rolls back and re-asks for the link."""
    company_name = data.get("company_name", "your company")
    link = (text or "").strip()
    if not _valid_url(link):
        messaging.send_prompt(user.phone, copy.EMP_LINK_INVALID)
        return "emp_link_invalid"
    try:
        _create_link_advocate(user, data, link)
    except SQLAlchemyError:
        logger.exception("wa: failed to save referral link for user %s", user.id)
        db.session.rollback()
        conversation.set_state(conv, "employee", "emp_link", data)
        messaging.send_prompt(user.phone, copy.EMP_SAVE_FAILED.format(company=company_name))
        return "emp_link_save_failed"
    conversation.reset_state(conv)
    messaging.send_prompt(user.phone, copy.ADVOCATE_LINK_DONE.format(
        company=company_name, link=link))
    return "advocate_link_created"


def _valid_url(url):
    url = (url or "").strip()
    return bool(url) and len(url) <= 2048 and bool(_URL_RE.match(url))


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
    # Flow done — leave it; no auto Welcome (user can type 'menu' to do more).
    conversation.reset_state(conv)
    messaging.send_prompt(user.phone, copy.ADVOCATE_DONE.format(
        company=company_name, emails=", ".join(saved or emails)))
    return "advocate_created"


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
    role_title = (data.get("role_title") or "").strip() or None
    saved = []
    for email in emails:
        advocate = WaAdvocate.query.filter_by(
            user_id=user.id, company_id=company_id, email=email).first()
        if advocate:
            advocate.status = "active"
            if role_title:
                advocate.role_title = role_title
            advocate.updated_at = datetime.utcnow()
            db.session.commit()
            saved.append(email)
            continue
        db.session.add(WaAdvocate(
            user_id=user.id, company_id=company_id, email=email,
            role_title=role_title, status="active"))
        try:
            db.session.commit()
            saved.append(email)
        except IntegrityError:
            db.session.rollback()
    return saved


def _create_link_advocate(user, data, link):
    """Store the advocate's self-serve referral link (one per user+company)."""
    company_id = data.get("company_id")
    role_title = (data.get("role_title") or "").strip() or None
    advocate = (WaAdvocate.query
                .filter_by(user_id=user.id, company_id=company_id)
                .filter(WaAdvocate.referral_link.isnot(None)).first())
    if advocate:
        advocate.referral_link = link
        advocate.status = "active"
        if role_title:
            advocate.role_title = role_title
        advocate.updated_at = datetime.utcnow()
        db.session.commit()
        return advocate
    advocate = WaAdvocate(
        user_id=user.id, company_id=company_id, referral_link=link,
        role_title=role_title, status="active")
    db.session.add(advocate)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return advocate
