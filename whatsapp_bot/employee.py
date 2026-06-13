"""Employee path: register as an advocate for a company.

Get-or-creates the company (employees grow the company list), collects a role,
confirms via the WA_CT_EMPLOYEE_CONFIRM template, and creates a wa_advocate.
This is the "supply" the candidate company-search (Phase C) will match against.
"""
from sqlalchemy.exc import IntegrityError

from database.models import db

from . import conversation, copy, messaging
from .config import WaConfig
from .models import WaAdvocate, WaCompany


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
        conversation.set_state(conv, "employee", "emp_role", data)
        messaging.send_prompt(user.phone, copy.EMP_ROLE.format(company=company.name))
        return "emp_company"

    if step == "emp_role":
        data["role_title"] = text
        conversation.set_state(conv, "employee", "emp_confirm", data)
        _send_confirm(user, data)
        return "emp_role"

    if step == "emp_confirm":
        if payload == "EMP_CONFIRM":
            _create_advocate(user, data)
            conversation.set_state(conv, "employee", "emp_done", {})
            messaging.send_prompt(user.phone, copy.ADVOCATE_DONE.format(company=data.get("company_name", "")))
            return "advocate_created"
        if payload == "EMP_EDIT":
            conversation.set_state(conv, "employee", "emp_company", {})
            messaging.send_prompt(user.phone, copy.EMP_COMPANY)
            return "emp_edit"
        # Stray tap/text at confirm → re-show it.
        _send_confirm(user, data)
        return "emp_confirm"

    # emp_done or unexpected → gentle nudge (carries a Back-to-Menu button).
    messaging.send_prompt(user.phone, copy.MAIN_COMING_SOON)
    return "emp_done"


def _send_confirm(user, data):
    messaging.send_buttons(user.phone, WaConfig.WA_CT_EMPLOYEE_CONFIRM, {
        "1": data.get("company_name", "—"),
        "2": data.get("role_title", "—"),
        "3": user.email or "—",
    })


def _create_advocate(user, data):
    company_id = data.get("company_id")
    advocate = WaAdvocate.query.filter_by(user_id=user.id, company_id=company_id).first()
    if advocate:
        advocate.role_title = data.get("role_title")
        advocate.status = "active"
        db.session.commit()
        return advocate
    advocate = WaAdvocate(
        user_id=user.id,
        company_id=company_id,
        role_title=data.get("role_title"),
        status="active",
    )
    db.session.add(advocate)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return advocate
