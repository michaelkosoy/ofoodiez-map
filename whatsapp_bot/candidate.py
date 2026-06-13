"""Candidate path: search a target company (matched against active advocates),
then collect the role and the job-posting link. The résumé upload + submission
(emailing advocates) are the next slice — they need Supabase Storage + SendGrid.

A search that's unknown, or known-but-with-no-active-advocates, is logged to
wa_company_requests (the ops backfill queue) and the candidate is invited to try
another company.
"""
import re

from database.models import db

from . import conversation, copy, messaging
from .models import WaAdvocate, WaCompany, WaCompanyRequest


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


def handle(user, conv, payload, text):
    step = conv.step
    data = dict(conv.data or {})

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
        messaging.send_prompt(user.phone, copy.CAND_RESUME_SOON)
        return "cand_job_link"

    # cand_resume / cand_main / anything else: résumé + submit is the next slice.
    messaging.send_prompt(user.phone, copy.CAND_RESUME_SOON)
    return "cand_resume_pending"


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
