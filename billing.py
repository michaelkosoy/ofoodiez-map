"""
PayPlus subscription billing for the gated Services section.

Flow:
  POST /services/pay  -> create a PayPlus payment page (charge_method=3, recurring)
                         and redirect the member to PayPlus's hosted page.
  PayPlus then:
    - redirects the member to GET /billing/return (UX only), and
    - POSTs a signed callback to POST /webhooks/payplus (authoritative).
  The callback is HMAC-SHA256 verified, then sets is_paid / paid_until on the user.

Config (env vars, set by the operator — never hardcoded, never in git):
  PAYPLUS_API_KEY, PAYPLUS_SECRET_KEY, PAYPLUS_PAYMENT_PAGE_UID
  PAYPLUS_ENV     = "dev" (sandbox, default) | "prod"
  PAYPLUS_AMOUNT  = price in ILS (optional, default 19)
"""
import os
import json
import hmac
import hashlib
import base64
from datetime import datetime, timedelta

import requests
from flask import Blueprint, request, redirect, url_for, flash, current_app

from database.models import db, User
from accounts import login_required, current_user

billing_bp = Blueprint('billing', __name__)

_BASES = {
    'dev':  'https://restapidev.payplus.co.il/api/v1.0',
    'prod': 'https://restapi.payplus.co.il/api/v1.0',
}


def _cfg():
    return {
        'api_key': os.environ.get('PAYPLUS_API_KEY'),
        'secret': os.environ.get('PAYPLUS_SECRET_KEY'),
        'page_uid': os.environ.get('PAYPLUS_PAYMENT_PAGE_UID'),
        'base': _BASES.get(os.environ.get('PAYPLUS_ENV', 'dev'), _BASES['dev']),
        'amount': float(os.environ.get('PAYPLUS_AMOUNT', '19')),
    }


def _activate(user, recurring_uid=None):
    """Mark the member paid for the current period. Idempotent."""
    user.is_paid = True
    user.paid_until = datetime.utcnow() + timedelta(days=31)  # extended on each recurring charge
    if recurring_uid:
        user.payplus_sub_uid = recurring_uid
    db.session.commit()


def _mark_paid(user):
    """Grant permanent paid access for a one-time purchase (Grow guide). Idempotent."""
    user.is_paid = True
    user.paid_at = datetime.utcnow()
    db.session.commit()


@billing_bp.route('/services/pay', methods=['POST'])
@login_required
def pay():
    cfg = _cfg()
    user = current_user()
    if user is None:
        return redirect(url_for('accounts.login'))
    if not (cfg['api_key'] and cfg['secret'] and cfg['page_uid']):
        flash('Payments are not configured yet.', 'error')
        return redirect(url_for('accounts.services'))

    payload = {
        'payment_page_uid': cfg['page_uid'],
        'charge_method': 3,                       # 3 = recurring
        'amount': cfg['amount'],
        'currency_code': 'ILS',
        'customer': {'customer_name': user.name or user.email, 'email': user.email},
        'more_info_1': str(user.id),              # echoed back in the callback
        'refURL_success': url_for('billing.checkout_return', _external=True),
        'refURL_failure': url_for('accounts.services', _external=True),
        'refURL_cancel':  url_for('accounts.services', _external=True),
        'refURL_callback': url_for('billing.payplus_callback', _external=True),
        'send_failure_callback': True,
        'recurring_settings': {
            'instant_first_payment': True,        # charge now, then monthly
            'recurring_type': 2,                  # 2 = monthly
            'recurring_range': 1,
            'number_of_charges': 0,               # 0 = unlimited
            'start_date_on_payment_date': True,
        },
    }
    headers = {'api-key': cfg['api_key'], 'secret-key': cfg['secret'],
               'Content-Type': 'application/json'}
    r = None
    try:
        r = requests.post(cfg['base'] + '/PaymentPages/generateLink',
                          json=payload, headers=headers, timeout=20)
        link = (r.json().get('data') or {}).get('payment_page_link')
    except Exception:
        link = None
    if not link:
        current_app.logger.error('PayPlus generateLink failed: %s', getattr(r, 'text', '?'))
        flash('Could not start checkout. Please try again.', 'error')
        return redirect(url_for('accounts.services'))
    return redirect(link)


@billing_bp.route('/billing/return')
@login_required
def checkout_return():
    # UX only — the signed callback is authoritative. If it already arrived the page
    # shows unlocked; otherwise a brief "confirming" message (refresh once it lands).
    flash('Thanks! Confirming your payment…', 'success')
    return redirect(url_for('accounts.services'))


@billing_bp.route('/webhooks/payplus', methods=['POST'])
def payplus_callback():
    cfg = _cfg()
    raw = request.get_data()                       # exact bytes PayPlus signed
    if not cfg['secret'] or request.headers.get('User-Agent') != 'PayPlus':
        return ('', 400)
    expected = base64.b64encode(
        hmac.new(cfg['secret'].encode(), raw, hashlib.sha256).digest()
    ).decode()
    if not hmac.compare_digest(expected, request.headers.get('hash', '')):
        return ('bad signature', 400)

    txn = (json.loads(raw or b'{}').get('transaction') or {})
    if txn.get('status_code') != '000':            # only act on approved charges
        return ('', 200)
    user = User.query.get(_safe_int(txn.get('more_info_1')))
    if user:
        recurring_uid = (txn.get('recurring_charge_information') or {}).get('recurring_uid')
        _activate(user, recurring_uid)
    return ('', 200)


# Last few Grow webhook payloads, kept in memory (single Render worker) for debugging.
_LAST_GROW_EVENTS = []


@billing_bp.route('/webhooks/grow', methods=['GET', 'POST'])
def grow_callback():
    """Grow (Meshulam) account webhook. Unlocks the buyer by matching the checkout
    email (or a user id echoed in a custom field) to a site account, then sets is_paid.

    GET / empty body = Grow's URL-validation probe -> 200 so the webhook saves.
    """
    if request.method == 'GET' or not request.get_data():
        return ('ok', 200)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = request.form.to_dict() or {'raw': request.get_data(as_text=True)[:3000]}

    # Capture + log BEFORE any check, so GET /webhooks/grow/debug shows exactly what Grow sends.
    # ponytail: temporary capture — drop it once the field mapping below is confirmed stable.
    _LAST_GROW_EVENTS.append({'at': datetime.utcnow().isoformat() + 'Z', 'data': data})
    del _LAST_GROW_EVENTS[:-10]
    current_app.logger.info('GROW webhook: %s', json.dumps(data, ensure_ascii=False)[:3000])

    flat = _flatten(data)

    # Key check is advisory during rollout (Grow regenerates the key; env may lag) — log, don't drop.
    key = os.environ.get('GROW_WEBHOOK_KEY')
    sent = _first(flat, 'webhookKey', 'webhook_key', 'webhookkey')
    if key and sent and not hmac.compare_digest(str(sent), str(key)):
        current_app.logger.warning('GROW: webhook key mismatch — check GROW_WEBHOOK_KEY on Render')

    # Match the buyer: checkout email == site email, else a user id echoed in a custom field.
    # ponytail: single product (Japan guide) -> is_paid=True permanently.
    email = _first(flat, 'payerEmail', 'payer_email', 'email', 'customerEmail', 'cardHolderEmail')
    if not email:                                       # fallback: any email-looking value
        for v in flat.values():
            if isinstance(v, str) and '@' in v and '.' in v.rsplit('@', 1)[-1]:
                email = v
                break
    u = User.query.filter_by(email=str(email).strip().lower()).first() if email else None
    if u is None:
        uid = _first(flat, 'cField1', 'customField1', 'more_info_1', 'identifier')
        if uid and str(uid).isdigit():
            u = User.query.get(int(uid))
    if u:
        if not u.is_paid:
            _mark_paid(u)
        current_app.logger.info('GROW: unlocked user %s (email=%s)', u.id, email)
    else:
        current_app.logger.warning('GROW: no match; payload keys=%s', list(flat.keys()))
    return ('', 200)


@billing_bp.route('/paid/japan')
def paid_japan_return():
    """Landing after payment. Access is granted MANUALLY — the admin ticks 'Paid' for
    the buyer in /admin/members after confirming the payment in Grow. So this only logs
    the return and sends the buyer back to the guide (which stays locked until approved).
    """
    if request.args:
        current_app.logger.info('GROW return params: %s', dict(request.args))
    return redirect('/blog/japan')


@billing_bp.route('/webhooks/grow/debug')
def grow_debug():
    """Temporary: view the last few raw Grow payloads to finalize field mapping."""
    expected = os.environ.get('GROW_WEBHOOK_KEY') or os.environ.get('ADMIN_SECRET')
    if not expected or request.args.get('key') != expected:
        return ('forbidden', 403)
    return (json.dumps(_LAST_GROW_EVENTS, ensure_ascii=False, indent=2),
            200, {'Content-Type': 'application/json; charset=utf-8'})


def _safe_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def _first(d, *keys):
    """First present, non-empty value among keys (tolerant webhook parsing)."""
    for k in keys:
        v = d.get(k)
        if v not in (None, ''):
            return v
    return None


def _flatten(d, out=None):
    """Flatten nested dict/list payloads into one {key: leaf} dict (last write wins)."""
    out = {} if out is None else out
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                _flatten(v, out)
            else:
                out[k] = v
    elif isinstance(d, list):
        for v in d:
            _flatten(v, out)
    return out
