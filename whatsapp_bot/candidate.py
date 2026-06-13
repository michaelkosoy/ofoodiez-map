"""Candidate path: company search → role → job link → résumé → submit.

On résumé (a PDF), the application is recorded and emailed to the company's
active advocates at their company email (best-effort: Supabase Storage + SendGrid
are config-gated, so the flow still completes and the application is recorded
even if they're unset).
"""
import re
from datetime import datetime

from database.models import db

from . import conversation, copy, emailer, messaging, storage
from .config import WaConfig
from .models import (
    WaAdvocate,
    WaApplication,
    WaApplicationRecipient,
    WaCompany,
    WaCompanyRequest,
)


def _normalize(name):
    return " ".join((name or "").strip().lower().split())


def _valid_url(url):
    url = (url or "").strip()
    if not url or len(url) > 2048:
        return False
    return bool(re.match(r"^https://[^\s/]+\.[^\s/]+", url, re.IGNORECASE))


def start(user, conv):
    conversation.set_state(conv, "candidate", "cand_company", {})
    messaging.send_prompt(user.phone, copy.CAND_COMPANY)
    return "cand_start"


def handle(user, conv, inbound):
    step = conv.step
    data = dict(conv.data or {})
    payload = inbound.get("button_payload")
    text = (inbound.get("body") or "").strip()

    if step == "cand_company":
        return _handle_company(user, conv, data, text)

    if step == "cand_role":
        data["role_query"] = text
        conversation.set_state(conv, "candidate", "cand_job_link", data)
        messaging.send_prompt(user.phone, copy.CAND_JOB_LINK.format(company=data.get("company_name", "")))
        return "cand_role"

    if step == "cand_job_link":
        if not _valid_url(text):
            messaging.send_prompt(user.phone, copy.CAND_JOB_LINK_INVALID)
            return "cand_job_link_invalid"
        data["job_posting_url"] = text.strip()
        conversation.set_state(conv, "candidate", "cand_resume", data)
        messaging.send_prompt(user.phone, copy.CAND_RESUME_PROMPT)
        return "cand_job_link"

    if step == "cand_resume":
        return _handle_resume(user, conv, data, inbound)

    if step == "cand_explore_more":
        return _handle_explore(user, conv, payload)

    return start(user, conv)


def _handle_company(user, conv, data, text):
    norm = _normalize(text)
    company = WaCompany.query.filter_by(normalized_name=norm).first()
    if company:
        active = WaAdvocate.query.filter_by(company_id=company.id, status="active").count()
        if active > 0:
            data["company_id"] = company.id
            data["company_name"] = company.name
            conversation.set_state(conv, "candidate", "cand_role", data)
            messaging.send_prompt(user.phone, copy.CAND_ROLE.format(company=company.name))
            return "cand_company_found"
        _log_request(user, text, norm, company.id, "no_advocates")
        messaging.send_prompt(user.phone, copy.CAND_NO_ADVOCATES.format(company=company.name))
        return "cand_no_advocates"
    _log_request(user, text, norm, None, "unknown_company")
    messaging.send_prompt(user.phone, copy.CAND_NOT_FOUND.format(company=text.strip()))
    return "cand_not_found"


def _handle_resume(user, conv, data, inbound):
    num_media = inbound.get("num_media") or 0
    media_url = inbound.get("media_url")
    ctype = (inbound.get("media_content_type") or "").lower()

    if not num_media or not media_url:
        messaging.send_prompt(user.phone, copy.CAND_RESUME_PROMPT)
        return "cand_resume_waiting"
    if "pdf" not in ctype:
        messaging.send_prompt(user.phone, copy.CAND_RESUME_NOT_PDF)
        return "cand_resume_not_pdf"

    content, _ = storage.download_twilio_media(media_url)
    if content is None:
        messaging.send_prompt(user.phone, copy.CAND_RESUME_FAILED)
        return "cand_resume_download_failed"

    resume_path = storage.upload_resume(user.id, content) or media_url
    application = _create_application(user, data, resume_path)
    recipients = _notify_advocates(application, user, data, content)

    if WaConfig.WA_CT_EXPLORE_MORE:
        conversation.set_state(conv, "candidate", "cand_explore_more",
                               {"company_id": data.get("company_id"), "company_name": data.get("company_name")})
        messaging.send_buttons(user.phone, WaConfig.WA_CT_EXPLORE_MORE, {"1": str(recipients)})
    else:
        conversation.reset_state(conv)
        messaging.send_prompt(user.phone, copy.CAND_SUBMITTED.format(n=recipients))
        _send_menu(user)
    return "cand_submitted"


def _handle_explore(user, conv, payload):
    if payload == "EXPLORE_YES":
        return start(user, conv)
    conversation.reset_state(conv)
    messaging.send_prompt(user.phone, copy.CAND_FINISHED)
    _send_menu(user)
    return "cand_finished"


def _send_menu(user):
    """Drop the user back on the Welcome menu so they can pick any path next."""
    if WaConfig.WA_CT_WELCOME:
        messaging.send_buttons(user.phone, WaConfig.WA_CT_WELCOME)


def _create_application(user, data, resume_path):
    application = WaApplication(
        candidate_user_id=user.id,
        company_id=data.get("company_id"),
        role_query=data.get("role_query"),
        job_posting_url=data.get("job_posting_url"),
        resume_path=resume_path,
        resume_filename="resume.pdf",
        status="submitted",
    )
    db.session.add(application)
    db.session.commit()
    return application


def _notify_advocates(application, candidate_user, data, resume_bytes):
    advocates = WaAdvocate.query.filter_by(company_id=data.get("company_id"), status="active").all()
    name = f"{candidate_user.first_name or ''} {candidate_user.last_name or ''}".strip() or "A candidate"
    for advocate in advocates:
        to_email = advocate.email
        ok = emailer.send_application_email(
            to_email, name, data.get("role_query", ""), data.get("company_name", ""),
            data.get("job_posting_url", ""), resume_bytes=resume_bytes,
        )
        db.session.add(WaApplicationRecipient(
            application_id=application.id,
            advocate_id=advocate.id,
            email=to_email,
            emailed_at=datetime.utcnow() if ok else None,
            email_status="sent" if ok else "pending",
        ))
    db.session.commit()
    return len(advocates)


def _log_request(user, raw, norm, company_id, reason):
    request = WaCompanyRequest(
        candidate_user_id=user.id,
        company_name_raw=(raw or "").strip(),
        normalized_name=norm,
        resolved_company_id=company_id,
        reason=reason,
        status="open",
    )
    db.session.add(request)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
