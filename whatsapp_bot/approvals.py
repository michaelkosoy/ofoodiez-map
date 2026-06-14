"""Referral-approval link handling.

The advocate's application email carries a tokenised link
(/wa/referral/approve?t=<token>). Opening it (GET) shows a confirm page; the
form POST marks the referral approved and emails the candidate that they've been
referred. Two steps on purpose: email-client link prefetchers issue GETs, so the
GET only renders a page — the human's POST is what actually confirms.

The link is a capability (the unguessable token IS the auth); these routes are
not Twilio webhooks, so they don't do signature verification.
"""
import html
import logging
from datetime import datetime

from flask import Response, request

from database.models import db

from . import emailer, wa_bp
from .models import (
    WaAdvocate,
    WaApplication,
    WaApplicationRecipient,
    WaCompany,
    WaUser,
)

logger = logging.getLogger("whatsapp_bot")


@wa_bp.route("/referral/approve", methods=["GET"])
def referral_approve_page():
    rec = _lookup(request.args.get("t", ""))
    if rec is None:
        return _page("Link not found", "This referral link is invalid or has expired.")
    if rec.approved_at:
        return _page("Already confirmed",
                     "You've already confirmed this referral — thank you! 🙏")
    ctx = _context(rec)
    return _confirm_page(rec.approval_token, ctx)


@wa_bp.route("/referral/approve", methods=["POST"])
def referral_approve_submit():
    rec = _lookup(request.form.get("t", ""))
    if rec is None:
        return _page("Link not found", "This referral link is invalid or has expired.")
    ctx = _context(rec)
    if not rec.approved_at:
        rec.approved_at = datetime.utcnow()
        db.session.commit()
        _notify_candidate(rec, ctx)
    return _page(
        "Thank you! 🎉",
        f"Thanks for confirming — we've let {html.escape(ctx['candidate'])} know "
        f"they've been referred at {html.escape(ctx['company'])}. 🙏<br><br>"
        f"Now go bag that referral bonus 💸 — tech referrals are basically "
        f"corporate bounty hunting via PDF. 🤠",
    )


def _lookup(token):
    token = (token or "").strip()
    if not token:
        return None
    return WaApplicationRecipient.query.filter_by(approval_token=token).first()


def _context(rec):
    """Names for the confirm/success pages + the candidate email."""
    application = WaApplication.query.get(rec.application_id)
    candidate = WaUser.query.get(application.candidate_user_id) if application else None
    company = WaCompany.query.get(application.company_id) if application else None
    advocate = WaAdvocate.query.get(rec.advocate_id)
    adv_user = WaUser.query.get(advocate.user_id) if advocate else None
    return {
        "application": application,
        "candidate": (candidate.first_name if candidate else None) or "the candidate",
        "candidate_email": candidate.email if candidate else None,
        "candidate_name": candidate.first_name if candidate else None,
        "company": (company.name if company else None) or "the company",
        "role": (application.role_query if application else None) or "the role",
        "advocate": (adv_user.first_name if adv_user else None) or "your advocate",
    }


def _notify_candidate(rec, ctx):
    if not ctx["candidate_email"]:
        return
    try:
        emailer.send_referral_confirmed_email(
            to_email=ctx["candidate_email"],
            candidate_name=ctx["candidate_name"] or "there",
            advocate_name=ctx["advocate"],
            company=ctx["company"],
            role=ctx["role"],
        )
    except Exception:
        logger.exception("wa: failed to send referral-confirmed email")


# ---------- tiny branded HTML responses ----------

def _shell(title, inner):
    return Response(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title></head>"
        "<body style='margin:0;font-family:Arial,Helvetica,sans-serif;background:#faf7f5;'>"
        "<div style='max-width:480px;margin:48px auto;padding:32px;background:#fff;"
        "border-radius:16px;box-shadow:0 6px 24px rgba(0,0,0,.06);text-align:center;'>"
        "<div style='font-size:28px;font-weight:bold;color:#ff7a59;margin-bottom:8px;'>Ofoodiez Referrals</div>"
        f"{inner}"
        "</div></body></html>",
        mimetype="text/html",
    )


def _page(title, message):
    return _shell(title,
                  f"<h2 style='color:#222;'>{html.escape(title)}</h2>"
                  f"<p style='color:#444;font-size:16px;line-height:1.5;'>{message}</p>")


def _confirm_page(token, ctx):
    inner = (
        "<h2 style='color:#222;'>Confirm referral</h2>"
        f"<p style='color:#444;font-size:16px;line-height:1.5;'>Did you refer "
        f"<b>{html.escape(ctx['candidate'])}</b> for <b>{html.escape(ctx['role'])}</b> "
        f"at <b>{html.escape(ctx['company'])}</b>?</p>"
        "<form method='POST' action='/wa/referral/approve' style='margin-top:24px;'>"
        f"<input type='hidden' name='t' value='{html.escape(token)}'>"
        "<button type='submit' style='background:#ff7a59;color:#fff;border:none;"
        "padding:14px 26px;border-radius:10px;font-size:16px;font-weight:bold;"
        "cursor:pointer;'>✅ Yes, I referred them</button>"
        "</form>"
        "<p style='color:#888;font-size:13px;margin-top:16px;'>We'll let them know they've been referred.</p>"
    )
    return _shell("Confirm referral", inner)
