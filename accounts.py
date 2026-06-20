"""
Site member accounts: registration, login, and the paid-gated Services section.

Mirrors the admin auth pattern (admin/auth.py) but uses its own session key
('user_id') so it is completely independent of the shared admin password login.
Passwords are hashed with werkzeug.security (ships with Flask — no new dependency).

# ponytail: no CSRF tokens here — matches the existing admin login, which has none.
# Add Flask-WTF if these forms ever attract abuse.
"""
import os
import re
import secrets
from functools import wraps
from urllib.parse import urlencode

import requests
from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash
)
from sqlalchemy.exc import IntegrityError

from database.models import db, User

accounts_bp = Blueprint('accounts', __name__)

# Trust-boundary sanity check, not full RFC validation.
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_MIN_PASSWORD = 8


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('accounts.login', next=request.url))
        return f(*args, **kwargs)
    return wrapper


def current_user():
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None


@accounts_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('accounts.services'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        name = (request.form.get('name') or '').strip()

        if not _EMAIL_RE.match(email):
            flash('Please enter a valid email address.', 'error')
        elif len(password) < _MIN_PASSWORD:
            flash(f'Password must be at least {_MIN_PASSWORD} characters.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('That email is already registered. Try logging in.', 'error')
        else:
            user = User(email=email, name=name)
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:  # race: same email registered concurrently
                db.session.rollback()
                flash('That email is already registered. Try logging in.', 'error')
                return render_template('register.html')
            session['user_id'] = user.id
            return redirect(url_for('accounts.services'))

    return render_template('register.html')


@accounts_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('accounts.services'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            next_url = request.args.get('next')
            return redirect(next_url or url_for('accounts.services'))
        flash('Invalid email or password.', 'error')

    return render_template('login.html')


@accounts_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))


@accounts_bp.route('/services')
@login_required
def services():
    user = current_user()
    if user is None:  # session points at a deleted account
        session.pop('user_id', None)
        return redirect(url_for('accounts.login'))
    # Paid gating happens in the template via user.has_access().
    return render_template('services.html', user=user)


# ---- Google OAuth (Sign in with Google) ----
# Plain OAuth2/OIDC over the existing `requests` dep — no new package.
_GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"


def _google_config():
    return (os.environ.get("GOOGLE_OAUTH_CLIENT_ID"),
            os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"))


@accounts_bp.route('/auth/google')
def google_login():
    client_id, client_secret = _google_config()
    if not (client_id and client_secret):
        flash('Google sign-in is not configured yet.', 'error')
        return redirect(url_for('accounts.login'))
    state = secrets.token_urlsafe(24)
    session['oauth_state'] = state
    session['oauth_next'] = request.args.get('next') or ''
    params = {
        'client_id': client_id,
        'redirect_uri': url_for('accounts.google_callback', _external=True),
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account',
    }
    return redirect(_GOOGLE_AUTH + '?' + urlencode(params))


@accounts_bp.route('/auth/google/callback')
def google_callback():
    client_id, client_secret = _google_config()
    if not (client_id and client_secret):
        flash('Google sign-in is not configured yet.', 'error')
        return redirect(url_for('accounts.login'))
    # CSRF: the state we get back must match the one we issued
    if not request.args.get('state') or request.args.get('state') != session.pop('oauth_state', None):
        flash('Google sign-in failed (bad state). Please try again.', 'error')
        return redirect(url_for('accounts.login'))
    code = request.args.get('code')
    if not code:
        return redirect(url_for('accounts.login'))
    redirect_uri = url_for('accounts.google_callback', _external=True)
    try:
        tok = requests.post(_GOOGLE_TOKEN, data={
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        }, timeout=15).json()
        access_token = tok.get('access_token')
        if not access_token:
            raise ValueError('no access token')
        info = requests.get(_GOOGLE_USERINFO,
                            headers={'Authorization': f'Bearer {access_token}'},
                            timeout=15).json()
    except Exception:
        flash('Could not complete Google sign-in. Please try again.', 'error')
        return redirect(url_for('accounts.login'))

    email = (info.get('email') or '').strip().lower()
    if not email or not info.get('email_verified', True):
        flash('Your Google account has no verified email.', 'error')
        return redirect(url_for('accounts.login'))

    user = User.query.filter_by(email=email).first()
    if user is None:                       # new account, no password
        user = User(email=email, name=info.get('name'), google_id=info.get('sub'))
        db.session.add(user)
        db.session.commit()
    elif not user.google_id:               # link Google to an existing email/password account
        user.google_id = info.get('sub')
        db.session.commit()

    session['user_id'] = user.id
    next_url = session.pop('oauth_next', '') or ''
    if not next_url.startswith('/') or next_url.startswith('//'):  # avoid open redirect
        next_url = url_for('accounts.services')
    return redirect(next_url)
