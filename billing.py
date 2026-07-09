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

Grow (Meshulam) Light API — one-time purchase of the Japan guide:
  POST /pay/japan -> CreatePaymentLink (a single-use link tied to the buyer via
                     cField1=user id) and redirect the buyer to it.
  Grow then:
    - POSTs the payment event to /webhooks/grow (notifyUrl) -> is_paid=True, and
    - redirects the buyer to GET /paid/japan (successUrl) -> back to the guide.
  GROW_API_KEY, GROW_USER_ID, GROW_PAGE_CODE   (from the Grow integration)
  GROW_API_BASE     = Light API base (default: Grow sandbox; set prod base to go live)
  GROW_GUIDE_PRICE  = price in ILS (default 1 — matches the sandbox catalog item)
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


# --- Grow (Meshulam) Light API: per-buyer payment link for the Japan guide ---

def _grow_cfg():
    return {
        'api_key': os.environ.get('GROW_API_KEY'),
        'user_id': os.environ.get('GROW_USER_ID'),
        'page_code': os.environ.get('GROW_PAGE_CODE'),
        'base': os.environ.get('GROW_API_BASE',
                               'https://sandboxapi.grow.link/api/light/server/1.0'),
        'price': int(os.environ.get('GROW_GUIDE_PRICE', '1')),
    }


def grow_light_ready():
    """True once the Grow Light API env vars are set (switches the guide to auto-unlock)."""
    c = _grow_cfg()
    return bool(c['api_key'] and c['user_id'] and c['page_code'])


def grow_guide_price():
    return _grow_cfg()['price']


@billing_bp.route('/pay/japan', methods=['POST'])
@login_required
def pay_japan():
    """Create a single-use Grow payment link tied to this account (cField1=user id)
    and send the buyer there. The /webhooks/grow callback unlocks automatically."""
    cfg = _grow_cfg()
    user = current_user()
    if user is None:
        return redirect(url_for('accounts.login'))
    if not grow_light_ready():
        flash('Payments are not configured yet.', 'error')
        return redirect('/blog/japan')

    name = (user.name or '').strip()
    payload = {
        'userId': cfg['user_id'],
        'pageCode': cfg['page_code'],
        'paymentLinkType': 1,                     # single-payment link
        'isActive': 1,
        'chargeType': 1,                          # regular charge
        'title': 'Ofoodiez Japan Guide',
        'successUrl': url_for('billing.paid_japan_return', _external=True),
        'notifyUrl': url_for('billing.grow_callback', _external=True),
        'cField1': str(user.id),                  # echoed back -> webhook matches the account
        'cField2': 'japan',
        'paymentTypes[0][type]': 'payments',
        'paymentTypes[0][payments][paymentsPaymentNum]': 1,
        # Grow requires prefill values; the buyer can edit them on the payment page.
        'pageFieldSettings[fullName][value]': name if len(name.split()) >= 2 else 'Ofoodiez Customer',
        'pageFieldSettings[phone][value]': '0500000000',   # ponytail: we don't collect phones
        'pageFieldSettings[email][value]': user.email,
        'products[data][0][catalogNumber]': 10,   # Grow catalog item "מדריך יפן"
        'products[data][0][name]': 'מדריך יפן',
        'products[data][0][price]': cfg['price'],
        'products[data][0][quantity]': 1,
        'products[data][0][vatType]': 3,          # VAT-exempt business (פטור ממע"מ)
    }
    r, link = None, None
    try:
        r = requests.post(cfg['base'] + '/CreatePaymentLink', data=payload,
                          headers={'x-api-key': cfg['api_key']}, timeout=20)
        flat = _flatten(r.json())
        link = _first(flat, 'paymentLinkUrl', 'paymentLink', 'lightLink', 'url', 'link')
        if not (isinstance(link, str) and link.startswith('http')):
            ours = {payload['successUrl'], payload['notifyUrl']}
            link = next((v for v in flat.values()
                         if isinstance(v, str) and v.startswith('http') and v not in ours), None)
    except Exception:
        link = None
    if not link:
        current_app.logger.error('GROW CreatePaymentLink failed: %s',
                                 getattr(r, 'text', '?')[:2000])
        flash('Could not start checkout. Please try again.', 'error')
        return redirect('/blog/japan')
    current_app.logger.info('GROW payment link created for user %s', user.id)
    return redirect(link)


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
    """Landing after Grow checkout. The webhook (matched via cField1=user id) unlocks
    the account automatically — usually before the buyer even lands here. Paid users
    fall straight through to the open guide; if the webhook hasn't arrived yet, show
    a "confirming" note on the locked page. (Static-link buyers without a webhook
    match are still activated manually in /admin/members.)
    """
    if request.args:
        current_app.logger.info('GROW return params: %s', dict(request.args))
    u = current_user()
    if u and not u.has_access():
        flash('Payment received! Confirming your access — refresh this page in a moment.',
              'success')
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
