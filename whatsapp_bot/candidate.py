"""Candidate path: company search → role → job link → résumé → submit.

On résumé (a PDF), the application is recorded and emailed to the company's
active advocates at their company email (best-effort: Supabase Storage + SendGrid
are config-gated, so the flow still completes and the application is recorded
even if they're unset).
"""
import difflib
import re
import secrets
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
    WaUser,
)


# Accepted CV file types (Twilio MediaContentType0 -> file extension).
_RESUME_TYPES = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

# "Did you mean X?" confirmation words; and words that skip the optional job link.
_CONFIRM_WORDS = {"yes", "y", "yep", "yeah", "yup", "ok", "okay", "sure", "correct", "👍"}
_SKIP_WORDS = {"pass", "skip", "no", "none", "n/a", "na", "-", "later"}


def _normalize(name):
    return " ".join((name or "").strip().lower().split())


def _valid_url(url):
    url = (url or "").strip()
    if not url or len(url) > 2048:
        return False
    return bool(re.match(r"^https://[^\s/]+\.[^\s/]+", url, re.IGNORECASE))


def start(user, conv, returning=True):
    """Begin the candidate path. Returning (already-registered) users get a
    by-name welcome-back; a freshly-registered user gets the welcome-aboard."""
    conversation.set_state(conv, "candidate", "cand_company", {})
    first = (user.first_name or "").strip()
    if returning and first:
        msg = copy.CAND_WELCOME_BACK.format(first=first)
    else:
        msg = copy.CAND_COMPANY
    messaging.send_prompt(user.phone, msg)
    return "cand_start"


def handle(user, conv, inbound):
    step = conv.step
    data = dict(conv.data or {})
    payload = inbound.get("button_payload")
    text = (inbound.get("body") or "").strip()

    if step == "cand_company":
        return _handle_company(user, conv, data, text)

    if step == "cand_company_suggest":
        return _handle_suggestion(user, conv, data, text)

    if step == "cand_role":
        data["role_query"] = text
        conversation.set_state(conv, "candidate", "cand_job_link", data)
        messaging.send_prompt(user.phone, copy.CAND_JOB_LINK.format(company=data.get("company_name", "")))
        return "cand_role"

    if step == "cand_job_link":
        # Optional: a URL → store it; "pass"/etc → skip; anything else → role description.
        t = text.strip()
        if _valid_url(t):
            data["job_posting_url"] = t
        elif t.lower() in _SKIP_WORDS:
            pass
        else:
            data["job_description"] = t
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
        return _resolve_company(user, conv, data, company)
    # No exact match → offer close matches instead of forcing exact spelling.
    similar = _find_similar(norm)
    if similar:
        data["suggestions"] = [c.id for c in similar]
        conversation.set_state(conv, "candidate", "cand_company_suggest", data)
        messaging.send_prompt(user.phone, _suggest_text(similar))
        return "cand_company_suggest"
    # Genuinely unknown → log + flag ops.
    _log_request(user, text, norm, None, "unknown_company")
    _notify_ops(user, text.strip(), "unknown_company")
    messaging.send_prompt(user.phone, copy.CAND_NOT_FOUND.format(company=text.strip()))
    return "cand_not_found"


def _resolve_company(user, conv, data, company):
    """Route a chosen company: self-serve link → email advocate → no advocates."""
    # Prefer a self-serve referral link: hand it over instantly, no waiting.
    link_adv = (WaAdvocate.query
                .filter_by(company_id=company.id, status="active")
                .filter(WaAdvocate.referral_link.isnot(None)).first())
    if link_adv:
        conversation.reset_state(conv)
        messaging.send_prompt(user.phone, copy.CAND_REFERRAL_LINK.format(
            advocate=_advocate_name(link_adv), company=company.name,
            link=link_adv.referral_link))
        return "cand_referral_link"
    # Otherwise an email advocate: collect role/CV and email them.
    advocate = (WaAdvocate.query
                .filter_by(company_id=company.id, status="active")
                .filter(WaAdvocate.email.isnot(None)).first())
    if advocate:
        data["company_id"] = company.id
        data["company_name"] = company.name
        data["advocate_name"] = _advocate_name(advocate)
        data.pop("suggestions", None)
        conversation.set_state(conv, "candidate", "cand_role", data)
        messaging.send_prompt(user.phone, copy.CAND_ROLE.format(
            company=company.name, advocate=data["advocate_name"]))
        return "cand_company_found"
    _log_request(user, company.name, company.normalized_name, company.id, "no_advocates")
    _notify_ops(user, company.name, "no_advocates")
    messaging.send_prompt(user.phone, copy.CAND_NO_ADVOCATES.format(company=company.name))
    return "cand_no_advocates"


def _handle_suggestion(user, conv, data, text):
    """Resolve a 'did you mean' reply: a number picks from the list, 'yes' picks the
    sole suggestion, anything else is treated as a brand-new company search."""
    suggestions = data.get("suggestions") or []
    t = text.strip().lower()
    chosen_id = None
    if t.isdigit():
        idx = int(t) - 1
        if 0 <= idx < len(suggestions):
            chosen_id = suggestions[idx]
    elif len(suggestions) == 1 and t in _CONFIRM_WORDS:
        chosen_id = suggestions[0]
    if chosen_id:
        company = WaCompany.query.get(chosen_id)
        if company:
            return _resolve_company(user, conv, data, company)
    # Not a selection → re-run the search with whatever they typed.
    data.pop("suggestions", None)
    conversation.set_state(conv, "candidate", "cand_company", data)
    return _handle_company(user, conv, data, text)


def _find_similar(norm, limit=3):
    """Companies close to the typed name: fast substring match first, then a
    bounded fuzzy/typo pass. Companies that have active advocates are preferred."""
    if not norm:
        return []
    hits = (WaCompany.query
            .filter(WaCompany.normalized_name.contains(norm))
            .limit(20).all())
    if not hits:
        qtokens = set(norm.split())
        scored = []
        for c in WaCompany.query.all():  # company table is small; bounded scan
            n = c.normalized_name or ""
            if not n:
                continue
            ratio = difflib.SequenceMatcher(None, norm, n).ratio()
            score = max(ratio, 0.85 if (qtokens & set(n.split())) else 0.0)
            if n in norm or score >= 0.6:
                scored.append((score, c))
        scored.sort(key=lambda sc: -sc[0])
        hits = [c for _, c in scored[: limit * 2]]
    # advocate-having companies first (more useful suggestions), order otherwise kept
    hits = sorted(hits, key=lambda c: 0 if _has_active_advocate(c.id) else 1)
    return hits[:limit]


def _has_active_advocate(company_id):
    return WaAdvocate.query.filter_by(company_id=company_id, status="active").first() is not None


def _suggest_text(similar):
    if len(similar) == 1:
        return copy.CAND_DID_YOU_MEAN_ONE.format(company=similar[0].name)
    options = "\n".join(f"{i}. {c.name}" for i, c in enumerate(similar, 1))
    return copy.CAND_DID_YOU_MEAN_MANY.format(options=options)


def _advocate_name(advocate):
    """First name of the advocate behind a wa_advocates row (for the candidate-
    facing 'I found {name}' message). Falls back gracefully."""
    adv_user = WaUser.query.get(advocate.user_id) if advocate else None
    first = (adv_user.first_name or "").strip() if adv_user else ""
    return first or "one of our advocates"


def _notify_ops(user, company_name, reason):
    """Best-effort heads-up to ops about a company we can't serve yet."""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "A candidate"
    try:
        emailer.send_company_request_email(company_name, name, user.phone, user.email, reason)
    except Exception:
        pass  # never let the ops notification break the candidate flow


def _handle_resume(user, conv, data, inbound):
    num_media = inbound.get("num_media") or 0
    media_url = inbound.get("media_url")
    ctype = (inbound.get("media_content_type") or "").split(";")[0].strip().lower()

    if not num_media or not media_url:
        messaging.send_prompt(user.phone, copy.CAND_RESUME_PROMPT)
        return "cand_resume_waiting"
    ext = _RESUME_TYPES.get(ctype)
    if ext is None:
        messaging.send_prompt(user.phone, copy.CAND_RESUME_BAD_TYPE)
        return "cand_resume_bad_type"

    content, _ = storage.download_twilio_media(media_url)
    if content is None:
        messaging.send_prompt(user.phone, copy.CAND_RESUME_FAILED)
        return "cand_resume_download_failed"

    resume_filename = f"resume{ext}"
    resume_path = storage.upload_resume(user.id, content, ctype, ext) or media_url
    application = _create_application(user, data, resume_path, resume_filename)
    recipients = _notify_advocates(application, user, data, content, ctype, resume_filename)

    if WaConfig.WA_CT_EXPLORE_MORE:
        conversation.set_state(conv, "candidate", "cand_explore_more",
                               {"company_id": data.get("company_id"), "company_name": data.get("company_name")})
        messaging.send_buttons(user.phone, WaConfig.WA_CT_EXPLORE_MORE, {"1": str(recipients)})
    else:
        # Flow done — leave it; no auto Welcome (user can type 'menu' to do more).
        conversation.reset_state(conv)
        messaging.send_prompt(user.phone, copy.CAND_SUBMITTED.format(
            advocate=data.get("advocate_name", "the advocate"),
            company=data.get("company_name", "the company")))
    return "cand_submitted"


def _handle_explore(user, conv, payload):
    if payload == "EXPLORE_YES":
        return start(user, conv)
    conversation.reset_state(conv)
    messaging.send_prompt(user.phone, copy.CAND_FINISHED)
    return "cand_finished"


def _create_application(user, data, resume_path, resume_filename):
    application = WaApplication(
        candidate_user_id=user.id,
        company_id=data.get("company_id"),
        role_query=data.get("role_query"),
        job_posting_url=data.get("job_posting_url"),
        job_description=data.get("job_description"),
        resume_path=resume_path,
        resume_filename=resume_filename,
        status="submitted",
    )
    db.session.add(application)
    db.session.commit()
    return application


def _notify_advocates(application, candidate_user, data, resume_bytes,
                      resume_content_type, resume_filename):
    advocates = (WaAdvocate.query
                 .filter_by(company_id=data.get("company_id"), status="active")
                 .filter(WaAdvocate.email.isnot(None)).all())
    name = f"{candidate_user.first_name or ''} {candidate_user.last_name or ''}".strip() or "A candidate"
    for advocate in advocates:
        to_email = advocate.email
        adv_user = WaUser.query.get(advocate.user_id)
        adv_first = (adv_user.first_name if adv_user else None) or ""
        token = secrets.token_urlsafe(24)
        approval_url = f"{WaConfig.WA_PUBLIC_BASE_URL}/wa/referral/approve?t={token}"
        ok = emailer.send_application_email(
            to_email, adv_first, name, candidate_user.email or "",
            data.get("role_query", ""), data.get("company_name", ""),
            data.get("job_posting_url", ""), job_description=data.get("job_description", ""),
            approval_url=approval_url, resume_bytes=resume_bytes,
            resume_filename=resume_filename, resume_content_type=resume_content_type,
        )
        db.session.add(WaApplicationRecipient(
            application_id=application.id,
            advocate_id=advocate.id,
            email=to_email,
            emailed_at=datetime.utcnow() if ok else None,
            email_status="sent" if ok else "pending",
            approval_token=token,
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
