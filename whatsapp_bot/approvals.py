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
import os
from datetime import datetime

from flask import Response, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from database.models import db

from . import emailer, storage, wa_bp
from .models import (
    WaAdvocate,
    WaApplication,
    WaApplicationRecipient,
    WaCompany,
    WaUser,
)

logger = logging.getLogger("whatsapp_bot")

_CV_MAX_AGE = 24 * 3600  # CV download links expire after 24h


def _cv_serializer():
    # Same default as app.py so signing (candidate.py) and verifying (here) agree
    # whether the bot runs in the main app or its own service.
    secret = os.environ.get("SECRET_KEY", "ofoodiez-dev-secret-change-in-prod")
    return URLSafeTimedSerializer(secret, salt="wa-cv-download")


def sign_cv_token(application_id):
    """A 24h-expiring signed token that authorises downloading one application's CV."""
    return _cv_serializer().dumps(int(application_id))


def _verify_cv_token(token, application_id):
    try:
        signed_id = _cv_serializer().loads(token or "", max_age=_CV_MAX_AGE)
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return False
    return int(signed_id) == int(application_id)


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


@wa_bp.route("/referral/deny", methods=["GET"])
def referral_deny_page():
    rec = _lookup(request.args.get("t", ""))
    if rec is None:
        return _page("Link not found", "This referral link is invalid or has expired.")
    if rec.approved_at:
        return _page("Already confirmed",
                     "You already confirmed this referral, so we can't mark it as "
                     "not-submitted. If that was a mistake, just reply to the email.")
    if rec.denied_at:
        return _page("Thanks", "You've already told us you didn't submit this — noted. 🙏")
    return _deny_confirm_page(rec.approval_token, _context(rec))


@wa_bp.route("/referral/deny", methods=["POST"])
def referral_deny_submit():
    rec = _lookup(request.form.get("t", ""))
    if rec is None:
        return _page("Link not found", "This referral link is invalid or has expired.")
    if rec.approved_at:
        return _page("Already confirmed",
                     "You already confirmed this referral, so we can't mark it as not-submitted.")
    if not rec.denied_at:
        rec.denied_at = datetime.utcnow()
        db.session.commit()
    return _page(
        "Thanks for flagging it",
        "Got it — we've marked this as something you didn't submit and won't count "
        "it as a referral. Sorry for the noise, and thanks for letting us know. 🙏",
    )


@wa_bp.route("/applications/<int:app_id>/cv", methods=["GET"])
def application_cv(app_id):
    """Token-guarded CV download for the link in the advocate email. The signed
    token (24h) IS the auth — no login. Streams the file server-side so the
    advocate never hits a Twilio/Supabase auth prompt."""
    if not _verify_cv_token(request.args.get("t", ""), app_id):
        return _page("Link expired",
                     "This CV download link is invalid or has expired (they last 24h). "
                     "The CV is also attached to the original email.")
    app_row = WaApplication.query.get(app_id)
    path = (app_row.resume_path if app_row else "") or ""
    if not path:
        return _page("Not found", "There's no CV on file for this application.")
    if path.startswith("http"):
        content, ctype = storage.download_twilio_media(path)
    else:
        content, ctype = storage.download_object(path)
    if content is None:
        return _page("Unavailable",
                     "We couldn't fetch the CV right now — please use the attachment instead.")
    filename = (app_row.resume_filename if app_row else None) or "cv.pdf"
    return Response(content, mimetype=ctype or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


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


def _deny_confirm_page(token, ctx):
    inner = (
        "<h2 style='color:#222;'>Didn't submit this?</h2>"
        f"<p style='color:#444;font-size:16px;line-height:1.5;'>Confirm that you did "
        f"<b>not</b> submit an application for <b>{html.escape(ctx['candidate'])}</b> "
        f"at <b>{html.escape(ctx['company'])}</b>. We'll flag it and won't count it as a referral.</p>"
        "<form method='POST' action='/wa/referral/deny' style='margin-top:24px;'>"
        f"<input type='hidden' name='t' value='{html.escape(token)}'>"
        "<button type='submit' style='background:#c0392b;color:#fff;border:none;"
        "padding:14px 26px;border-radius:10px;font-size:16px;font-weight:bold;"
        "cursor:pointer;'>I didn't submit this</button>"
        "</form>"
    )
    return _shell("Didn't submit this", inner)
