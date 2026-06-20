"""
Site member accounts: registration, login, and the paid-gated Services section.

Mirrors the admin auth pattern (admin/auth.py) but uses its own session key
('user_id') so it is completely independent of the shared admin password login.
Passwords are hashed with werkzeug.security (ships with Flask — no new dependency).

# ponytail: no CSRF tokens here — matches the existing admin login, which has none.
# Add Flask-WTF if these forms ever attract abuse.
"""
import re
from functools import wraps

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


@accounts_bp.route('/services/pay', methods=['POST'])
@login_required
def pay():
    """MOCK payment: flips the member to paid and unlocks /services.

    # ponytail: mock only — this is the seam for the real provider. Replace with a
    # redirect to a hosted checkout (Grow/Meshulam, Stripe, ...) plus a webhook route
    # that sets is_paid / paid_until on confirmed payment.
    """
    user = current_user()
    if user is None:
        session.pop('user_id', None)
        return redirect(url_for('accounts.login'))
    user.is_paid = True
    db.session.commit()
    return redirect(url_for('accounts.services'))
