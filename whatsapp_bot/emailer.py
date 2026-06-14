"""Advocate notification emails via SendGrid (best-effort, config-gated).

If SENDGRID_API_KEY / WA_FROM_EMAIL aren't set, send_application_email returns
False and the caller records the recipient as 'pending' — the application is
still saved, the email just isn't sent.
"""
import base64
import logging

import requests

from .config import WaConfig

logger = logging.getLogger("whatsapp_bot")

_SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


def send_application_email(to_email, candidate_name, role, company, job_url,
                           job_description="", resume_bytes=None,
                           resume_filename="resume.pdf",
                           resume_content_type="application/pdf"):
    """Email an advocate a candidate's application (CV attached). Returns True if
    sent, False if SendGrid isn't configured or the send failed."""
    api_key = WaConfig.SENDGRID_API_KEY
    from_email = WaConfig.WA_FROM_EMAIL
    if not api_key or not from_email or not to_email:
        return False

    if job_url:
        detail = f"Job posting: {job_url}\n\n"
    elif job_description:
        detail = f"Role details: {job_description}\n\n"
    else:
        detail = ""
    body = (
        f"Hi,\n\n"
        f"{candidate_name} is interested in a {role or 'role'} at {company} and "
        f"would love your referral.\n\n"
        f"{detail}"
        f"Their CV is attached. Sent via Ofoodiez Referrals."
    )
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Ofoodiez Referrals"},
        "subject": f"New candidate for {role or 'a role'} at {company}",
        "content": [{"type": "text/plain", "value": body}],
    }
    if resume_bytes:
        payload["attachments"] = [{
            "content": base64.b64encode(resume_bytes).decode("ascii"),
            "type": resume_content_type or "application/octet-stream",
            "filename": resume_filename or "resume.pdf",
            "disposition": "attachment",
        }]

    return _post(payload)


def send_company_request_email(company_name, candidate_name, candidate_phone,
                               candidate_email, reason):
    """Notify ops (WA_OPS_EMAIL, default contact@ofoodiez.com) that a candidate
    searched a company we can't yet serve, so it can be backfilled. Best-effort:
    returns False if SendGrid / the ops address aren't configured."""
    api_key = WaConfig.SENDGRID_API_KEY
    from_email = WaConfig.WA_FROM_EMAIL
    to_email = WaConfig.WA_OPS_EMAIL
    if not api_key or not from_email or not to_email:
        return False

    reason_label = {
        "unknown_company": "is NOT in our database yet",
        "no_advocates": "is in our database but has NO advocates yet",
    }.get(reason, reason)
    body = (
        f"A candidate requested a referral we can't fulfil yet.\n\n"
        f"Company requested: {company_name}\n"
        f"Status: that company {reason_label}.\n\n"
        f"Candidate: {candidate_name}\n"
        f"WhatsApp: {candidate_phone}\n"
        f"Email: {candidate_email or '—'}\n\n"
        f"Consider adding the company / recruiting an advocate there. "
        f"Sent via Ofoodiez Referrals."
    )
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Ofoodiez Referrals"},
        "subject": f"Referral request: {company_name} ({reason})",
        "content": [{"type": "text/plain", "value": body}],
    }
    return _post(payload)


def _post(payload):
    api_key = WaConfig.SENDGRID_API_KEY
    try:
        resp = requests.post(
            _SENDGRID_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        if resp.status_code in (200, 201, 202):
            return True
        logger.warning("wa SendGrid send failed: %s %s", resp.status_code, resp.text[:200])
        return False
    except Exception:
        logger.exception("wa: SendGrid send error")
        return False
