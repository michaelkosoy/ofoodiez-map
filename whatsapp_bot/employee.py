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


def get_company(name):
    """Lookup only — never creates. Used while the advocate is still mid-flow so
    an abandoned sign-up never leaves an orphan company with zero advocates."""
    return WaCompany.query.filter_by(normalized_name=_normalize(name)).first()


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


def _ensure_company(data):
    """Create the company row now, at the point an advocate is actually about to
    be attached to it — not at emp_company. This is what prevents an abandoned
    sign-up (name typed, then dropped off) from leaving a company with zero
    advocates in the admin list."""
    if not data.get("company_id"):
        company = get_or_create_company(data.get("company_name") or "")
        data["company_id"] = company.id
        data["company_name"] = company.name
    return data["company_id"]


def start(user, conv):
    # Returning advocate → show what they submitted so they can edit/remove it.
    # One company jumps straight to the edit menu; several → pick which first.
    company_ids = _advocate_company_ids(user)
    logger.info("wa employee.start: user=%s companies=%s", user.id, company_ids)
    if len(company_ids) == 1:
        return _open_edit_menu(user, conv, company_ids[0])
    if company_ids:
        conversation.set_state(conv, "employee", "emp_edit_pick",
                               {"edit_company_ids": company_ids})
        # ponytail: plain text, not send_prompt. This menu is always shown in-window
        # (they just tapped a button), and its rich {details} body was being silently
        # rejected as a WA_CT_PROMPT template variable — leaving advocates stuck.
        messaging.send_text(user.phone, _companies_list_text(user, company_ids))
        return "emp_edit_pick"
    # New advocate → sign them up (router already gated on is_registered).
    conversation.set_state(conv, "employee", "emp_company", {})
    messaging.send_prompt(user.phone, copy.EMP_COMPANY)
    return "emp_start"


def handle(user, conv, payload, text):
    step = conv.step
    data = dict(conv.data or {})

    if step == "emp_company":
        company = get_company(text)
        data["company_id"] = company.id if company else None
        data["company_name"] = company.name if company else text.strip()
        conversation.set_state(conv, "employee", "emp_details", data)
        messaging.send_prompt(user.phone, copy.EMP_DETAILS.format(company=data["company_name"]))
        return "emp_company"

    if step == "emp_details":
        return _handle_details(user, conv, data, text)

    if step == "emp_details_confirm":
        return _handle_details_confirm(user, conv, data, text, payload)

    if step == "emp_email":
        return _handle_email(user, conv, data, text)

    if step == "emp_method":
        choice = _method_choice(text, payload)
        company_name = data.get("company_name", "your company")
        if choice == "email":
            # Email is its own question (the work inbox where CVs land).
            conversation.set_state(conv, "employee", "emp_email", data)
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

    # --- edit / remove an existing submission ---
    if step == "emp_edit_pick":
        return _handle_edit_pick(user, conv, data, text)
    if step == "emp_edit_menu":
        return _handle_edit_menu(user, conv, data, text)
    if step == "emp_edit_title":
        return _apply_edit_title(user, conv, data, text)
    if step == "emp_edit_link":
        return _apply_edit_link(user, conv, data, text)
    if step == "emp_edit_emails":
        return _apply_edit_emails(user, conv, data, text)
    if step == "emp_edit_remove_confirm":
        return _handle_edit_remove(user, conv, data, text, payload)

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


# ---- Combined advocate details: name + email + title in ONE message ----

_TITLE_WORDS = {
    "senior", "junior", "lead", "principal", "staff", "head", "chief", "vp",
    "director", "manager", "engineer", "developer", "dev", "devops", "sre",
    "analyst", "scientist", "designer", "architect", "specialist", "consultant",
    "recruiter", "hr", "pm", "product", "data", "software", "qa", "marketing",
    "sales", "finance", "operations", "cto", "ceo", "coo", "founder", "intern",
    "associate", "backend", "frontend", "fullstack", "full-stack", "ml", "ai",
    "researcher", "team", "tech", "technical", "project", "program", "owner",
}


def _looks_like_title(seg):
    return any(tok.lower().strip(".,") in _TITLE_WORDS for tok in seg.split())


def _split_name_title(seg):
    """Split one no-separator chunk into (name, title) at the first title keyword,
    e.g. 'Gil Zohar DevOps Manager' → ('Gil Zohar', 'DevOps Manager')."""
    toks = seg.split()
    for i, t in enumerate(toks):
        if i > 0 and t.lower().strip(".,") in _TITLE_WORDS:
            return " ".join(toks[:i]), " ".join(toks[i:])
    if len(toks) <= 2:                       # just a name, no title given
        return seg, None
    return " ".join(toks[:2]), " ".join(toks[2:])  # assume the first two are the name


def _parse_details(text):
    """Best-effort pull of first/last name, email, title from one free-text
    message. Handles commas / newlines / pipes / ' - ' and no-separator forms."""
    raw = (text or "").strip()
    out = {"first_name": None, "last_name": None, "email": None, "title": None}
    m = re.search(r"[^\s,;|/]+@[^\s,;|/]+\.[^\s,;|/]+", raw)
    if m:
        out["email"] = m.group(0).strip().strip(".").lower()
        raw = (raw[:m.start()] + "  " + raw[m.end():]).strip()
    segments = [t for s in re.split(r"[,\n;|]+|\s[-–—]\s", raw)
                if (t := s.strip().strip("-–—").strip())]
    name_part = title_part = None
    if len(segments) >= 2:
        idx = next((i for i, s in enumerate(segments) if _looks_like_title(s)), None)
        if idx is not None:
            title_part = segments[idx]
            name_part = " ".join(s for i, s in enumerate(segments) if i != idx) or None
        else:
            name_part, title_part = segments[0], " ".join(segments[1:]) or None
    elif segments:
        name_part, title_part = _split_name_title(segments[0])
    if name_part:
        toks = name_part.split()
        out["first_name"] = toks[0]
        out["last_name"] = " ".join(toks[1:]) or None
    if title_part:
        out["title"] = title_part.strip()
    return out


def _handle_details(user, conv, data, text):
    parsed = _parse_details(text)  # any email typed here is ignored — asked separately
    full = " ".join(x for x in (parsed["first_name"], parsed["last_name"]) if x) or None
    if not full:
        messaging.send_prompt(user.phone, copy.EMP_DETAILS.format(
            company=data.get("company_name", "your company")))
        return "emp_details"
    data.update({
        "first_name": parsed["first_name"], "last_name": parsed["last_name"],
        "role_title": parsed["title"], "full_name": full,
    })
    conversation.set_state(conv, "employee", "emp_details_confirm", data)
    messaging.send_prompt(user.phone, copy.EMP_DETAILS_CONFIRM.format(
        name=full, title=data.get("role_title") or "(none)"))
    return "emp_details"


def _handle_details_confirm(user, conv, data, text, payload):
    if not _is_confirm(text, payload):
        # Not a yes → treat the message as corrected details and re-parse.
        return _handle_details(user, conv, data, text)
    _persist_identity(user, data)
    conversation.set_state(conv, "employee", "emp_method", data)
    _send_method_choice(user, data.get("company_name", "your company"))
    return "emp_details_confirmed"


def _persist_identity(user, data):
    """Save the parsed name/email onto the user so they count as registered."""
    if data.get("first_name"):
        user.first_name = data["first_name"]
    if data.get("last_name"):
        user.last_name = data["last_name"]
    if data.get("email"):
        user.email = data["email"]
    user.terms_accepted_at = user.terms_accepted_at or datetime.utcnow()
    db.session.commit()


def _handle_email(user, conv, data, text):
    """The separate work-email question (email method) — the inbox CVs land in."""
    email = (text or "").strip().strip("<>").lower()
    if not _EMAIL_RE.match(email):
        messaging.send_prompt(user.phone, copy.EMP_EMAIL_INVALID.format(
            company=data.get("company_name", "your company")))
        return "emp_email_invalid"
    data["email"] = email
    user.email = email          # completes their sign-up (name saved on the confirm step)
    db.session.commit()
    return _finalize_email_advocate(user, conv, data)


def _finalize_email_advocate(user, conv, data):
    """Email method: create the advocate with the separately-collected email
    (one row per user+company+email)."""
    company_name = data.get("company_name", "your company")
    email = (data.get("email") or "").strip().lower() or None
    try:
        company_id = _ensure_company(data)
        advocate = WaAdvocate.query.filter_by(
            user_id=user.id, company_id=company_id, email=email).first()
        if not advocate:
            advocate = WaAdvocate(user_id=user.id, company_id=company_id,
                                  email=email, status="active")
            db.session.add(advocate)
        advocate.role_title = data.get("role_title") or advocate.role_title
        advocate.advocate_name = data.get("full_name") or advocate.advocate_name
        advocate.status = "active"
        advocate.updated_at = datetime.utcnow()
        db.session.commit()
    except SQLAlchemyError:
        logger.exception("wa: finalize email advocate failed for user %s", user.id)
        db.session.rollback()
        conversation.set_state(conv, "employee", "emp_method", data)
        messaging.send_prompt(user.phone, copy.EMP_SAVE_FAILED.format(company=company_name))
        return "emp_email_save_failed"
    conversation.reset_state(conv)
    messaging.send_prompt(user.phone, copy.ADVOCATE_DONE.format(
        company=company_name, emails=email or "—"))
    return "advocate_created"


def _save_link(user, conv, data, text):
    """Validate + persist a self-serve referral link. Never hiccups on a DB
    error — rolls back and re-asks for the link."""
    company_name = data.get("company_name", "your company")
    link = (text or "").strip()
    if not _valid_url(link):
        messaging.send_prompt(user.phone, copy.EMP_LINK_INVALID)
        return "emp_link_invalid"
    try:
        _ensure_company(data)
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
        _ensure_company(data)
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
    email = (data.get("email") or "").strip().lower() or None
    full_name = (data.get("full_name") or "").strip() or None
    advocate = (WaAdvocate.query
                .filter_by(user_id=user.id, company_id=company_id)
                .filter(WaAdvocate.referral_link.isnot(None)).first())
    if advocate:
        advocate.referral_link = link
        advocate.status = "active"
        if role_title:
            advocate.role_title = role_title
        if email:               # only set when provided (edit-link leaves it untouched)
            advocate.email = email
        if full_name:
            advocate.advocate_name = full_name
        advocate.updated_at = datetime.utcnow()
        db.session.commit()
        return advocate
    advocate = WaAdvocate(
        user_id=user.id, company_id=company_id, referral_link=link,
        role_title=role_title, email=email, advocate_name=full_name, status="active")
    db.session.add(advocate)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return advocate


# ---------------- Edit / remove an existing submission ----------------

def _advocate_company_ids(user):
    """Distinct companies this user is an ACTIVE advocate for, in a stable order."""
    rows = WaAdvocate.query.filter_by(user_id=user.id, status="active").all()
    seen, ids = set(), []
    for a in rows:
        if a.company_id not in seen:
            seen.add(a.company_id)
            ids.append(a.company_id)
    return ids


def _company_name(company_id):
    c = WaCompany.query.get(company_id)
    return c.name if c else "your company"


def _advocate_summary(user_id, company_id):
    """(title, link, [emails]) across this user's active rows for one company."""
    rows = WaAdvocate.query.filter_by(
        user_id=user_id, company_id=company_id, status="active").all()
    title = next((a.role_title for a in rows if (a.role_title or "").strip()), None)
    link = next((a.referral_link for a in rows if a.referral_link), None)
    emails = [a.email for a in rows if a.email]
    return title, link, emails


def _companies_list_text(user, company_ids):
    lines = []
    for i, cid in enumerate(company_ids, 1):
        title, link, emails = _advocate_summary(user.id, cid)
        method = "link" if link else ("email" if emails else "—")
        label = _company_name(cid) + (f", {title}" if title else "")
        lines.append(f"{i}. {label} ({method})")
    return copy.EMP_EDIT_LIST.format(companies="\n".join(lines))


def _send_edit_menu(user, company_id, company_name, prefix=""):
    title, link, emails = _advocate_summary(user.id, company_id)
    details = ["• Role: " + (title if title else "(none set)")]
    if link:
        details.append(f"• Link: {link}")
    if emails:
        details.append(f"• Email: {', '.join(emails)}")
    if not link and not emails:
        details.append("• (no link or email yet)")
    # ponytail: plain text, not send_prompt — see start(); the edit menu is in-window
    # and its {details} body was being dropped as a WA_CT_PROMPT template variable.
    messaging.send_text(user.phone, prefix + copy.EMP_EDIT_MENU.format(
        company=company_name, details="\n".join(details)))


def _open_edit_menu(user, conv, company_id, prefix=""):
    company_name = _company_name(company_id)
    conversation.set_state(conv, "employee", "emp_edit_menu",
                           {"editing": True, "company_id": company_id, "company_name": company_name})
    _send_edit_menu(user, company_id, company_name, prefix)
    return "emp_edit_menu"


def _start_new_company(user, conv):
    conversation.set_state(conv, "employee", "emp_company", {})
    messaging.send_prompt(user.phone, copy.EMP_COMPANY)
    return "emp_company"


def _handle_edit_pick(user, conv, data, text):
    ids = data.get("edit_company_ids") or []
    t = (text or "").strip().lower()
    if t in ("add", "new"):
        return _start_new_company(user, conv)
    if t.isdigit() and 1 <= int(t) <= len(ids):
        return _open_edit_menu(user, conv, ids[int(t) - 1])
    messaging.send_prompt(user.phone, _companies_list_text(user, ids))
    return "emp_edit_pick"


def _handle_edit_menu(user, conv, data, text):
    t = (text or "").strip().lower()
    company_id = data.get("company_id")
    company_name = data.get("company_name", "your company")
    if t == "title":
        conversation.set_state(conv, "employee", "emp_edit_title", data)
        messaging.send_prompt(user.phone, copy.EMP_EDIT_TITLE.format(company=company_name))
        return "emp_edit_title"
    if t == "link":
        conversation.set_state(conv, "employee", "emp_edit_link", data)
        messaging.send_prompt(user.phone, copy.EMP_LINK_PROMPT.format(company=company_name))
        return "emp_edit_link"
    if t in ("email", "emails"):
        conversation.set_state(conv, "employee", "emp_edit_emails", data)
        messaging.send_prompt(user.phone, copy.EMP_EMAIL.format(company=company_name))
        return "emp_edit_emails"
    if t == "remove":
        conversation.set_state(conv, "employee", "emp_edit_remove_confirm", data)
        messaging.send_prompt(user.phone, copy.EMP_EDIT_REMOVE_CONFIRM.format(company=company_name))
        return "emp_edit_remove_confirm"
    if t in ("add", "new"):
        return _start_new_company(user, conv)
    _send_edit_menu(user, company_id, company_name)  # unrecognized → re-show
    return "emp_edit_menu"


def _apply_edit_title(user, conv, data, text):
    company_id = data.get("company_id")
    t = (text or "").strip()
    new_title = None if t.lower() in _SKIP_WORDS else (t or None)
    for a in WaAdvocate.query.filter_by(
            user_id=user.id, company_id=company_id, status="active").all():
        a.role_title = new_title
        a.updated_at = datetime.utcnow()
    db.session.commit()
    return _open_edit_menu(user, conv, company_id, prefix="✅ Title updated!\n\n")


def _apply_edit_link(user, conv, data, text):
    company_name = data.get("company_name", "your company")
    link = (text or "").strip()
    if not _valid_url(link):
        messaging.send_prompt(user.phone, copy.EMP_LINK_INVALID)
        return "emp_edit_link_invalid"
    data["role_title"] = _advocate_summary(user.id, data["company_id"])[0]  # keep title on a new row
    try:
        _create_link_advocate(user, data, link)
    except SQLAlchemyError:
        logger.exception("wa: edit link failed for user %s", user.id)
        db.session.rollback()
        messaging.send_prompt(user.phone, copy.EMP_SAVE_FAILED.format(company=company_name))
        return "emp_edit_link_failed"
    return _open_edit_menu(user, conv, data["company_id"], prefix="✅ Link updated!\n\n")


def _apply_edit_emails(user, conv, data, text):
    company_name = data.get("company_name", "your company")
    valid, had_personal = _parse_emails(text)
    if not valid:
        msg = copy.EMP_EMAIL_PERSONAL if had_personal else copy.EMP_EMAIL_INVALID
        messaging.send_prompt(user.phone, msg.format(company=company_name))
        return "emp_edit_emails_invalid"
    data["role_title"] = _advocate_summary(user.id, data["company_id"])[0]  # keep title on new rows
    try:
        _create_advocates(user, data, valid)
    except SQLAlchemyError:
        logger.exception("wa: edit emails failed for user %s", user.id)
        db.session.rollback()
        messaging.send_prompt(user.phone, copy.EMP_SAVE_FAILED.format(company=company_name))
        return "emp_edit_emails_failed"
    return _open_edit_menu(user, conv, data["company_id"], prefix="✅ Email updated!\n\n")


def _handle_edit_remove(user, conv, data, text, payload):
    company_id = data.get("company_id")
    company_name = data.get("company_name", "your company")
    if not _is_confirm(text, payload):
        # Not a confirmation → keep it, back to the edit menu (menu/restart escape globally).
        return _open_edit_menu(user, conv, company_id)
    for a in WaAdvocate.query.filter_by(
            user_id=user.id, company_id=company_id, status="active").all():
        a.status = "inactive"
        a.updated_at = datetime.utcnow()
    db.session.commit()
    conversation.reset_state(conv)
    messaging.send_prompt(user.phone, copy.EMP_EDIT_REMOVED.format(company=company_name))
    return "emp_edit_removed"
