"""Advocate notification emails via SendGrid (best-effort, config-gated).

If SENDGRID_API_KEY / WA_FROM_EMAIL aren't set, send_application_email returns
False and the caller records the recipient as 'pending' — the application is
still saved, the email just isn't sent.
"""
import base64
import html
import logging

import requests

from .config import WaConfig

logger = logging.getLogger("whatsapp_bot")

_SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


def send_application_email(to_email, advocate_name, candidate_name, candidate_email,
                           role, company, job_url, job_description="", approval_url="",
                           resume_bytes=None, resume_filename="resume.pdf",
                           resume_content_type="application/pdf"):
    """Email an advocate a candidate's application (CV attached). Includes the
    candidate's email and an "I referred them" confirmation button (approval_url).
    Returns True if sent, False if SendGrid isn't configured or the send failed.

    Sends both a text/plain and a text/html part so the button renders.
    """
    api_key = WaConfig.SENDGRID_API_KEY
    from_email = WaConfig.WA_FROM_EMAIL
    if not api_key or not from_email or not to_email:
        return False

    if job_url:
        detail_txt = f"Job posting: {job_url}\n"
        detail_html = f'<p>🔗 Job posting: <a href="{html.escape(job_url)}">{html.escape(job_url)}</a></p>'
    elif job_description:
        detail_txt = f"Role details: {job_description}\n"
        detail_html = f"<p>📝 Role details: {html.escape(job_description)}</p>"
    else:
        detail_txt, detail_html = "", ""

    confirm_txt = (
        f"\n✅ Did you refer them? Confirm here and we'll let them know:\n{approval_url}\n"
        if approval_url else ""
    )
    confirm_html = (
        f'<p style="margin:24px 0;">'
        f'<a href="{html.escape(approval_url)}" '
        f'style="background:#ff7a59;color:#fff;text-decoration:none;padding:12px 22px;'
        f'border-radius:8px;font-weight:bold;display:inline-block;">'
        f'✅ Yes, I referred them</a></p>'
        f'<p style="font-size:13px;color:#666;">Tapping this confirms you referred '
        f'{html.escape(candidate_name)} — we\'ll let them know. 🎉</p>'
        if approval_url else ""
    )

    text_body = (
        f"Hey {advocate_name or 'there'}! 😊\n\n"
        f"{candidate_name} is interested in a {role or 'role'} at {company} and "
        f"would love a referral from you.\n\n"
        f"Candidate email: {candidate_email or '—'}\n"
        f"{detail_txt}\n"
        f"Their CV is attached.\n"
        f"{confirm_txt}\n"
        f"Thanks so much for being an Ofoodiez advocate — you're helping someone "
        f"land their dream job! 🙏\n\n"
        f"— The Ofoodiez team"
    )
    cand_email_html = (
        f'<a href="mailto:{html.escape(candidate_email)}">{html.escape(candidate_email)}</a>'
        if candidate_email else "—"
    )
    html_body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#222;line-height:1.55;">'
        f"<p>Hey {html.escape(advocate_name or 'there')}! 😊</p>"
        f"<p><b>{html.escape(candidate_name)}</b> is interested in a "
        f"<b>{html.escape(role or 'role')}</b> at <b>{html.escape(str(company))}</b> "
        f"and would love a referral from you.</p>"
        f"<p>📧 Candidate email: {cand_email_html}</p>"
        f"{detail_html}"
        f"<p>📎 Their CV is attached.</p>"
        f"{confirm_html}"
        "<p>Thanks so much for being an Ofoodiez advocate — you're helping someone "
        "land their dream job! 🙏</p>"
        "<p>— The Ofoodiez team</p>"
        "</div>"
    )
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Ofoodiez Referrals"},
        "subject": f"New candidate for {role or 'a role'} at {company}",
        "content": [
            {"type": "text/plain", "value": text_body},
            {"type": "text/html", "value": html_body},
        ],
    }
    if resume_bytes:
        payload["attachments"] = [{
            "content": base64.b64encode(resume_bytes).decode("ascii"),
            "type": resume_content_type or "application/octet-stream",
            "filename": resume_filename or "resume.pdf",
            "disposition": "attachment",
        }]

    return _post(payload)


def send_referral_confirmed_email(to_email, candidate_name, advocate_name, company, role):
    """Tell the candidate an advocate confirmed their referral. Best-effort.

    Sent as PLAIN TEXT ONLY with a personal subject (no HTML, no links, no emoji
    in the subject) so Gmail files it in Primary, not Promotions — this is the
    one a candidate must actually see.
    """
    api_key = WaConfig.SENDGRID_API_KEY
    from_email = WaConfig.WA_FROM_EMAIL
    if not api_key or not from_email or not to_email:
        return False

    text_body = (
        f"Hey {candidate_name or 'there'}! 😊\n\n"
        f"Great news — {advocate_name} from {company} just confirmed your referral "
        f"for {role or 'the role'}.\n\n"
        f"Fingers crossed — we're rooting for you. 🤞\n\n"
        f"— The Ofoodiez team"
    )
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Ofoodiez Referrals"},
        "subject": f"{advocate_name} referred you at {company}",
        "content": [{"type": "text/plain", "value": text_body}],
    }
    return _post(payload)


def send_company_available_email(to_email, candidate_name, company_name):
    """Tell a candidate that a company they asked about is now serviceable (has an
    advocate). Plain text + personal subject so it lands in Primary. Best-effort."""
    api_key = WaConfig.SENDGRID_API_KEY
    from_email = WaConfig.WA_FROM_EMAIL
    if not api_key or not from_email or not to_email:
        return False
    text_body = (
        f"Hey {candidate_name or 'there'}! 😊\n\n"
        f"Good news — {company_name} was added to Ofoodiez Referrals and we found an "
        f"advocate there who can refer you! 🎉\n\n"
        f"Message us on WhatsApp, ask for a referral to {company_name} and send your "
        f"CV again — it'll go straight to them.\n\n"
        f"— The Ofoodiez team"
    )
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Ofoodiez Referrals"},
        "subject": f"{company_name} is now on Ofoodiez — ask for your referral",
        "content": [{"type": "text/plain", "value": text_body}],
    }
    return _post(payload)


def send_company_request_email(company_name, candidate_name, candidate_phone,
                               candidate_email, reason):
    """Notify ops (WA_OPS_EMAIL, default info@ofoodiez.com) that a candidate
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
        "cv_no_email_advocate": "has only a self-serve referral link — this candidate's CV "
                                "is saved on the application for manual routing in the admin",
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


def send_contact_email(name, phone, email, message):
    """Forward a Contact-Us message from the WhatsApp bot to ops (WA_OPS_EMAIL).
    Reply-To is the user's email when we have one, so ops can reply directly.
    Best-effort: returns False if SendGrid / the ops address aren't configured."""
    api_key = WaConfig.SENDGRID_API_KEY
    from_email = WaConfig.WA_FROM_EMAIL
    to_email = WaConfig.WA_OPS_EMAIL
    if not api_key or not from_email or not to_email:
        return False
    body = (
        f"New Contact-Us message from the WhatsApp bot.\n\n"
        f"From: {name}\n"
        f"WhatsApp: {phone}\n"
        f"Email: {email or '—'}\n\n"
        f"Message:\n{message}\n"
    )
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Ofoodiez Contact"},
        "subject": f"Contact Us — {name}",
        "content": [{"type": "text/plain", "value": body}],
    }
    if email:
        payload["reply_to"] = {"email": email, "name": name}
    return _post(payload)


def send_hitech_signup_email(email, linkedin_url=""):
    """Notify ops that a new person joined the HiTech waitlist. Best-effort."""
    api_key = WaConfig.SENDGRID_API_KEY
    from_email = WaConfig.WA_FROM_EMAIL
    to_email = WaConfig.WA_OPS_EMAIL
    logger.info(
        "[hitech emailer] api_key=%s from=%s to=%s",
        bool(api_key), from_email, to_email,
    )
    if not api_key or not from_email or not to_email:
        logger.warning("[hitech emailer] missing config — email NOT sent")
        return False

    linkedin_line = f"\nLinkedIn: {linkedin_url}" if linkedin_url else ""
    body = (
        f"New HiTech waitlist signup!\n\n"
        f"Email: {email}"
        f"{linkedin_line}\n\n"
        f"— Ofoodiez"
    )
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Ofoodiez"},
        "subject": f"HiTech signup: {email}",
        "content": [{"type": "text/plain", "value": body}],
    }
    return _post(payload)


def send_hitech_rejection_email(to_email):
    """Send a rejection email to a HiTech signup whose LinkedIn was invalid."""
    api_key = WaConfig.SENDGRID_API_KEY
    from_email = WaConfig.WA_FROM_EMAIL
    if not to_email:
        return False
    if not api_key or not from_email:
        print("\n" + "="*60)
        print(" [REJECTION EMAIL MOCK / LOCAL DEV MODE]")
        print(f" To: {to_email}")
        print("="*60 + "\n")
        return True

    text_body = (
        "Hi,\n\n"
        "We noticed that you signed up for the Ofoodiez Tech community – food events for people in tech.\n\n"
        "Unfortunately, we couldn't approve your registration because the LinkedIn profile you provided was incorrect or invalid.\n\n"
        "As part of our verification process, we ask all members to provide their LinkedIn profile so we can verify participants' identities.\n\n"
        "Please register again using the link below and make sure to include your correct LinkedIn profile:\n"
        "https://ofoodiez.com/hitech\n\n"
        "Thank you, and we look forward to having you in the community!\n\n"
        "Best,\nOfoodiez"
    )
    html_body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#222;line-height:1.6;">'
        "<p>Hi,</p>"
        "<p>We noticed that you signed up for the <b>Ofoodiez Tech community</b> – food events for people in tech.</p>"
        "<p>Unfortunately, we couldn't approve your registration because the LinkedIn profile you provided was <b>incorrect or invalid</b>.</p>"
        "<p>As part of our verification process, we ask all members to provide their LinkedIn profile so we can verify participants' identities.</p>"
        "<p>Please register again using the link below and make sure to include your correct LinkedIn profile:</p>"
        '<p><a href="https://ofoodiez.com/hitech" style="background:#720815;color:#f9f6eb;text-decoration:none;'
        'padding:12px 24px;border-radius:8px;font-weight:bold;display:inline-block;">Register Again</a></p>'
        "<p>Thank you, and we look forward to having you in the community!</p>"
        "<p>Best,<br>Ofoodiez</p>"
        "</div>"
    )
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Ofoodiez"},
        "subject": "Your Ofoodiez Tech Community Registration was not approved",
        "content": [
            {"type": "text/plain", "value": text_body},
            {"type": "text/html", "value": html_body},
        ],
    }
    return _post(payload)


def send_custom_community_email(to_email, subject, body_html, body_text):
    """Send a custom community email to a tech member using SendGrid."""
    api_key = WaConfig.SENDGRID_API_KEY
    from_email = WaConfig.WA_FROM_EMAIL
    if not to_email:
        return False
    if not api_key or not from_email:
        print("\n" + "="*60)
        print(" [EMAIL MOCK / LOCAL DEV MODE]")
        print(f" To: {to_email}")
        print(f" Subject: {subject}")
        print(f" Body (Plain Text):\n{body_text}")
        print("="*60 + "\n")
        return True

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "Ofoodiez"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": body_text},
            {"type": "text/html", "value": html.escape(body_html) if "<" not in body_html else body_html},
        ],
    }
    return _post(payload)


def _post(payload):
    api_key = WaConfig.SENDGRID_API_KEY
    # Don't let SendGrid rewrite links into ct.sendgrid.net click-tracking URLs
    # (the advocate must see the real job link the candidate provided, and
    # rewritten links + open-tracking pixels hurt inbox placement).
    payload.setdefault("tracking_settings", {
        "click_tracking": {"enable": False, "enable_text": False},
        "open_tracking": {"enable": False},
    })
    # A real reply path (on the authenticated domain) reads as legitimate and
    # lets candidates/advocates reply straight to the team.
    reply_to = WaConfig.WA_OPS_EMAIL or WaConfig.WA_FROM_EMAIL
    if reply_to:
        payload.setdefault("reply_to", {"email": reply_to, "name": "Ofoodiez"})
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
