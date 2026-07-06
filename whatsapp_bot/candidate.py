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


def _valid_job_link(url):
    """A job-posting URL (company careers page or LinkedIn). Lenient on domain —
    we can't know each company's careers host — but it must be a real http(s) URL."""
    url = (url or "").strip()
    if not url or len(url) > 2048:
        return False
    return bool(re.match(r"^https?://[^\s/]+\.[^\s/]+", url, re.IGNORECASE))


# Answers that aren't a real company name — re-asked instead of logged as a
# backfill request ("all", "tech", "high tech", "don't know", a sentence, …).
# Sector/generic words are matched whole (squashed) so real companies that merely
# CONTAIN them (AllCloud, Startup Nation, Check Point Software) still pass.
_VAGUE_EXACT = {
    "all", "any", "anything", "everything", "everyone", "everywhere", "anywhere",
    "none", "nothing", "na", "idk", "whatever", "dunno", "tbd", "open", "many",
    "tech", "hitech", "hightech", "hightechcompanies", "startup", "startups",
    "company", "companies", "biotech", "biotechnology", "fintech", "cyber",
    "ai", "ml", "software", "hardware", "saas", "hr", "sales", "marketing",
}
# Apostrophe-free forms — matched against text with apostrophes stripped, so
# "don't know" / "I don't know" (straight OR curly ') are all caught.
_VAGUE_PHRASE = (
    "high tech", "high-tech", "hi tech", "hi-tech",
    "dont know", "no clue", "no idea", "not sure", "not specific",
    "nothing specific", "not a company", "looking for", "interested in",
    "no preference", "doesnt matter", "not relevant", "not important",
    "undecided", "not decided", "anywhere", "everywhere", "digital / branding",
    "digital/branding", "entry-lev", "project manager role",
)


def _is_vague_company(text):
    """True when the text clearly isn't a company name (a generic term or a whole
    sentence), so we re-ask instead of logging a bogus company request."""
    norm = _normalize(text)
    clean = norm
    for ch in ("’", "‘", "'", "`", "´"):  # curly/straight apostrophes
        clean = clean.replace(ch, "")
    squashed = re.sub(r"[^a-z0-9]", "", clean)
    if not squashed:
        return True
    if squashed in _VAGUE_EXACT or clean in _VAGUE_EXACT or norm in _VAGUE_EXACT:
        return True
    if any(p in clean for p in _VAGUE_PHRASE):
        return True
    return len(norm.split()) > 5 or len(text.strip()) > 45  # sentence-like


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

    if step == "cand_after_link":
        return _handle_after_link(user, conv, data, inbound)

    if step == "cand_match_role":
        return _match_and_route(user, conv, data, text)

    if step == "cand_role":
        data["role_query"] = text
        conversation.set_state(conv, "candidate", "cand_job_link", data)
        messaging.send_prompt(user.phone, copy.CAND_JOB_LINK.format(company=data.get("company_name", "")))
        return "cand_role"

    if step == "cand_job_link":
        # Required: a real job-posting URL (company careers page or LinkedIn).
        t = text.strip()
        if not _valid_job_link(t):
            messaging.send_prompt(user.phone, copy.CAND_JOB_LINK_REQUIRED)
            return "cand_job_link_invalid"
        data["job_posting_url"] = t
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
    # Reject vague / non-company answers ("all", "high tech", "don't know", a
    # whole sentence) — re-ask instead of logging a bogus company request.
    if _is_vague_company(text):
        messaging.send_prompt(user.phone, copy.CAND_COMPANY_VAGUE)
        return "cand_company_vague"
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
    """Route a chosen company. If any advocate has a title, ask the candidate's
    role first and match it; otherwise use the simple link → email → none path."""
    data["company_id"] = company.id
    data["company_name"] = company.name
    data.pop("suggestions", None)
    advocates = WaAdvocate.query.filter_by(company_id=company.id, status="active").all()

    # Titled advocates → ask the role so we can match them to the right person.
    if any((a.role_title or "").strip() for a in advocates):
        conversation.set_state(conv, "candidate", "cand_match_role", data)
        messaging.send_prompt(user.phone, copy.CAND_ROLE_MATCH.format(company=company.name))
        return "cand_match_role"

    # No titles → today's behavior: instant self-serve link, else email→CV, else none.
    link_adv = next((a for a in advocates if a.referral_link), None)
    if link_adv:
        return _send_link(user, conv, data, link_adv)
    advocate = next((a for a in advocates if a.email), None)
    if advocate:
        data["advocate_name"] = _advocate_name(advocate)
        conversation.set_state(conv, "candidate", "cand_role", data)
        messaging.send_prompt(user.phone, copy.CAND_ROLE.format(
            company=company.name, advocate=data["advocate_name"]))
        return "cand_company_found"
    _log_request(user, company.name, company.normalized_name, company.id, "no_advocates")
    _notify_ops(user, company.name, "no_advocates")
    messaging.send_prompt(user.phone, copy.CAND_NO_ADVOCATES.format(company=company.name))
    return "cand_no_advocates"


def _send_link(user, conv, data, adv):
    """Hand over an advocate's referral link (using whatever title/name we have)
    and keep the candidate in-flow so they can still send a CV for another role."""
    conversation.set_state(conv, "candidate", "cand_after_link", data)
    name = _advocate_first_name(adv)
    title = (adv.role_title or "").strip()
    company = data.get("company_name", "")
    link = adv.referral_link
    if name and title:
        msg = copy.CAND_REFERRAL_LINK_TITLED_NAMED.format(
            name=name, title=title, company=company, link=link)
    elif title:
        msg = copy.CAND_REFERRAL_LINK_TITLED.format(title=title, company=company, link=link)
    elif name:
        msg = copy.CAND_REFERRAL_LINK.format(advocate=name, company=company, link=link)
    else:
        msg = copy.CAND_REFERRAL_LINK_NONAME.format(company=company, link=link)
    messaging.send_prompt(user.phone, msg)
    return "cand_referral_link"


def _best_title_match(advocates, role_query):
    """Best advocate whose title matches the candidate's role, or None.
    exact > contains > fuzzy/token-overlap; ties prefer one with a referral link."""
    q = _normalize(role_query)
    if not q:
        return None
    best, best_score = None, 0.0
    for a in advocates:
        t = _normalize(a.role_title)
        if not t:
            continue
        if t == q:
            score = 1.0
        elif t in q or q in t:
            score = 0.9
        else:
            score = difflib.SequenceMatcher(None, q, t).ratio()
            if set(q.split()) & set(t.split()):
                score = max(score, 0.85)
        if a.referral_link:
            score += 0.001  # tie-break toward a self-serve link
        if score > best_score:
            best, best_score = a, score
    return best if best_score >= 0.8 else None


def _match_and_route(user, conv, data, role_query):
    """Candidate gave a target role at a company with titled advocates: match to
    the right person, falling back to a generic (untitled) link, then the CV path."""
    data["role_query"] = (role_query or "").strip()
    advocates = WaAdvocate.query.filter_by(
        company_id=data.get("company_id"), status="active").all()
    match = _best_title_match(advocates, data["role_query"])
    if match and match.referral_link:
        return _send_link(user, conv, data, match)
    if match and match.email:
        data["advocate_name"] = _advocate_first_name(match) or "the team"
        conversation.set_state(conv, "candidate", "cand_job_link", data)
        messaging.send_prompt(user.phone, copy.CAND_JOB_LINK.format(
            company=data.get("company_name", "")))
        return "cand_match_email"
    # No title match → a generic (untitled) link if there is one, else the CV path.
    generic = next((a for a in advocates
                    if a.referral_link and not (a.role_title or "").strip()), None)
    if generic:
        return _send_link(user, conv, data, generic)
    conversation.set_state(conv, "candidate", "cand_job_link", data)
    messaging.send_prompt(user.phone, copy.CAND_NO_MATCH_CV.format(
        role=data["role_query"], company=data.get("company_name", "")))
    return "cand_no_title_match"


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


def _handle_after_link(user, conv, data, inbound):
    """After we hand over a self-serve referral link, the candidate can still
    apply for a *different* role by CV. menu/restart are intercepted globally, so
    any reply that reaches here means "continue" — treat their text as the target
    role and drop into the normal role → job link → résumé path.
    ponytail: any non-empty reply is the role; no extra confirm button to maintain."""
    text = (inbound.get("body") or "").strip()
    if not text:
        # e.g. they sent a CV before naming a role — ask for the role first.
        messaging.send_prompt(user.phone, copy.CAND_AFTER_LINK_ROLE)
        return "cand_after_link"
    data["role_query"] = text
    data.setdefault("advocate_name", "the team")
    conversation.set_state(conv, "candidate", "cand_job_link", data)
    messaging.send_prompt(user.phone, copy.CAND_JOB_LINK.format(company=data.get("company_name", "")))
    return "cand_after_link_role"


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


def _advocate_first_name(advocate):
    """First name to show for a wa_advocates row, or '' when there's no person.
    Prefers the linked bot user; falls back to a curated advocate's display name."""
    if not advocate:
        return ""
    adv_user = WaUser.query.get(advocate.user_id) if advocate.user_id else None
    if adv_user and (adv_user.first_name or "").strip():
        return adv_user.first_name.strip()
    return (advocate.advocate_name or "").strip().split(" ")[0]  # "Gil Zellner" -> "Gil"


def _advocate_name(advocate):
    """First name of the advocate behind a wa_advocates row (for the candidate-
    facing 'I found {name}' message). Falls back gracefully."""
    return _advocate_first_name(advocate) or "one of our advocates"


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
    if not recipients:
        # Link-only company: no advocate email to forward to → flag ops. The CV is
        # still saved on the application for manual routing in the admin.
        _notify_ops(user, data.get("company_name", ""), "cv_no_email_advocate")

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
