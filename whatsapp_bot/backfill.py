"""Candidate backfill notifications — served by the BOT service (which has the
SendGrid env vars; the main-site admin does not).

Two secret-gated endpoints (no admin session, so they check ?key= against
WA_CRON_SECRET / ADMIN_SECRET — the SAME value must be set on this service, on
the main app, and on the external cron):

  POST /wa/requests/<id>/notify   the admin marked a request handled → email that
                                  one candidate their company is now available.
  GET/POST /wa/backfill-cron      sweep: email every open request whose company
                                  now has an active advocate, then mark handled.
"""
import logging
import os

from flask import jsonify, request

from database.models import db

from . import copy, emailer, messaging, wa_bp
from .config import WaConfig
from .models import WaAdvocate, WaCompany, WaCompanyRequest, WaUser

logger = logging.getLogger("whatsapp_bot")


def _secret():
    return os.environ.get("WA_CRON_SECRET") or os.environ.get("ADMIN_SECRET", "ofoodiez2025")


def _authorized():
    return request.args.get("key") == _secret()


def _resolve_company(req_row, company=None):
    if company is not None:
        return company
    if req_row.resolved_company_id:
        company = WaCompany.query.get(req_row.resolved_company_id)
    if company is None and req_row.normalized_name:
        company = WaCompany.query.filter_by(normalized_name=req_row.normalized_name).first()
    return company


def _notify(req_row, company=None):
    """Email + WhatsApp-ping the candidate that their requested company is now
    available. Returns 'sent' | 'no_email' | 'no_advocate' | 'failed' (the email's
    outcome — the WhatsApp ping is best-effort on top). Gated on an active
    advocate — we only tell a candidate 'available' once someone can actually
    refer them there."""
    cand = WaUser.query.get(req_row.candidate_user_id)
    if not cand:
        return "no_email"
    company = _resolve_company(req_row, company)
    if company is None or WaAdvocate.query.filter_by(
            company_id=company.id, status="active").first() is None:
        return "no_advocate"
    _ping_candidate(cand, company.name)
    if not cand.email:
        return "no_email"   # the WhatsApp ping above is their only notification
    ok = emailer.send_company_available_email(cand.email, cand.first_name or "there", company.name)
    return "sent" if ok else "failed"


def _ping_candidate(cand, company_name):
    """Short WhatsApp version of the company-available email. The
    WA_CT_COMPANY_AVAILABLE template reaches candidates outside the 24h session
    window; without it we fall back to free-form text (in-window only).
    Best-effort — never blocks the email path."""
    try:
        if WaConfig.WA_CT_COMPANY_AVAILABLE:
            messaging.send_buttons(cand.phone, WaConfig.WA_CT_COMPANY_AVAILABLE,
                                   {"1": cand.first_name or "there", "2": company_name})
        else:
            messaging.send_text(cand.phone, copy.COMPANY_AVAILABLE_PING.format(
                name=cand.first_name or "there", company=company_name))
    except Exception:
        logger.exception("wa backfill: candidate WhatsApp ping failed (%s)", cand.phone)


@wa_bp.route("/requests", methods=["POST"])
def add_request():
    """Ops: manually queue a backfill request for someone who asked OUTSIDE the
    bot. Creates the wa_users row if the phone is new. Keyed like the rest.
    JSON/form fields: company, phone (E.164), email?, first_name?, last_name?"""
    if not _authorized():
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    company = (data.get("company") or "").strip()
    phone = (data.get("phone") or "").strip()
    if not company or not phone:
        return jsonify({"error": "company and phone are required"}), 400
    user = WaUser.query.filter_by(phone=phone).first()
    if user is None:
        user = WaUser(phone=phone)
        db.session.add(user)
    for field in ("email", "first_name", "last_name"):
        if data.get(field) and not getattr(user, field):
            setattr(user, field, data[field].strip())
    db.session.flush()
    norm = " ".join(company.lower().split())
    comp = WaCompany.query.filter_by(normalized_name=norm).first()
    req_row = WaCompanyRequest(
        candidate_user_id=user.id,
        company_name_raw=company,
        normalized_name=norm,
        resolved_company_id=comp.id if comp else None,
        reason="manual",
        status="open",
    )
    db.session.add(req_row)
    db.session.commit()
    logger.info("wa backfill: manual request added company=%r user=%s", company, user.id)
    return jsonify({"id": req_row.id, "user_id": user.id, "company": company,
                    "company_exists": bool(comp)}), 201


@wa_bp.route("/requests/<int:req_id>/notify", methods=["POST"])
def notify_request(req_id):
    """Manual path: the admin flipped this request to handled; tell the candidate."""
    if not _authorized():
        return jsonify({"error": "forbidden"}), 403
    req_row = WaCompanyRequest.query.get_or_404(req_id)
    result = _notify(req_row)
    logger.info("wa backfill: manual notify request=%s -> %s", req_id, result)
    return jsonify({"result": result, "emailed": result == "sent"})


@wa_bp.route("/backfill-cron", methods=["GET", "POST"])
def backfill_cron():
    """Notify candidates whose requested company now has an active advocate, then
    mark those requests handled. Companies still without an advocate stay open."""
    if not _authorized():
        return jsonify({"error": "forbidden"}), 403
    handled = notified = 0
    for req_row in WaCompanyRequest.query.filter_by(status="open").all():
        company = _resolve_company(req_row)
        if company is None:
            continue
        if WaAdvocate.query.filter_by(company_id=company.id, status="active").first() is None:
            continue  # still no advocate — leave open for next run
        result = _notify(req_row, company)
        if result == "failed":
            continue  # transient (e.g. SendGrid hiccup) — leave open to retry
        req_row.status = "handled"
        db.session.commit()
        handled += 1
        if result == "sent":
            notified += 1
    logger.info("wa backfill-cron: handled=%d notified=%d", handled, notified)
    return jsonify({"handled": handled, "notified": notified})
