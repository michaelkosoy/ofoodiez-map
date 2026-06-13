"""Employee path: register as an advocate (someone who refers candidates).

Distinct from the candidate flow: collect the person's name, their company, and
a *company email* (where candidate applications are sent), confirm, then create
the advocate. No job link / résumé — that's the candidate side.
"""
import re
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from database.models import db

from . import conversation, copy, messaging
from .config import WaConfig
from .models import WaAdvocate, WaCompany

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
        conversation.set_state(conv, "employee", "emp_email", data)
        messaging.send_prompt(user.phone, copy.EMP_EMAIL.format(company=company.name))
        return "emp_company"

    if step == "emp_email":
        if not _EMAIL_RE.match(text.strip()):
            messaging.send_prompt(user.phone, copy.EMP_EMAIL_INVALID)
            return "emp_email_invalid"
        data["email"] = text.strip()
        conversation.set_state(conv, "employee", "emp_confirm", data)
        _send_confirm(user, data)
        return "emp_email"

    if step == "emp_confirm":
        if payload == "EMP_CONFIRM":
            _create_advocate(user, data)
            conversation.set_state(conv, "employee", "emp_done", {})
            messaging.send_prompt(user.phone, copy.ADVOCATE_DONE.format(
                company=data.get("company_name", ""), email=data.get("email", "")))
            return "advocate_created"
        if payload == "EMP_EDIT":
            conversation.set_state(conv, "employee", "emp_company", data)
            messaging.send_prompt(user.phone, copy.EMP_COMPANY)
            return "emp_edit"
        _send_confirm(user, data)
        return "emp_confirm"

    # emp_done / unexpected → nudge (carries a Back-to-Menu button).
    messaging.send_prompt(user.phone, copy.ADVOCATE_DONE.format(
        company=data.get("company_name", "your company"), email=data.get("email", "")))
    return "emp_done"


def _send_confirm(user, data):
    messaging.send_buttons(user.phone, WaConfig.WA_CT_EMPLOYEE_CONFIRM, {
        "1": data.get("company_name", "—"),
        "2": data.get("email", "—"),
    })


def _create_advocate(user, data):
    company_id = data.get("company_id")
    advocate = WaAdvocate.query.filter_by(user_id=user.id, company_id=company_id).first()
    if advocate:
        advocate.email = data.get("email")
        advocate.status = "active"
        db.session.commit()
        return advocate
    advocate = WaAdvocate(
        user_id=user.id,
        company_id=company_id,
        email=data.get("email"),
        status="active",
    )
    db.session.add(advocate)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return advocate
