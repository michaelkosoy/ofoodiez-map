"""
Instagram OAuth authentication routes.
Handles the Instagram Login flow: authorize → callback → token exchange → store user.
"""
import requests
from datetime import datetime, timedelta
from flask import redirect, request, session, url_for, flash, render_template, jsonify

from . import ig_bp
from .config import Config
from .database import db, User


@ig_bp.route('/auth/login')
def auth_login():
    """Redirect user to Instagram's authorization page."""
    missing = Config.validate()
    if missing:
        return jsonify({
            "error": "Missing configuration",
            "missing": missing,
            "hint": "Set these environment variables and restart the server."
        }), 500

    auth_url = Config.get_auth_url()
    return redirect(auth_url)


@ig_bp.route('/auth/mock-login', methods=['GET', 'POST'])
def auth_mock_login():
    """Bypass Meta OAuth and log in directly with a test account or custom username."""
    username = 'tester_account'
    if request.method == 'POST':
        username = request.form.get('username', 'tester_account').strip().replace('@', '')
        if not username:
            username = 'tester_account'

    # Check if a user with this username exists, otherwise create or update it
    user = User.query.filter_by(ig_username=username).first()
    if not user:
        import random
        mock_id = f"mock_{random.randint(100000, 999999)}"
        user = User(
            ig_user_id=mock_id,
            ig_username=username,
            access_token='test_token_123',
            token_expires_at=datetime.utcnow() + timedelta(days=60),
            is_active=True
        )
        db.session.add(user)
        db.session.commit()
    
    session['ig_user_id'] = user.id
    flash(f"Logged in as mock account @{username} successfully!", "success")
    return redirect(url_for('instagram_automation.dashboard_home'))




@ig_bp.route('/auth/callback')
def auth_callback():
    """Handle the OAuth callback from Instagram."""
    error = request.args.get('error')
    if error:
        error_reason = request.args.get('error_reason', 'Unknown')
        error_description = request.args.get('error_description', 'No details provided')
        return render_template('ig_error.html',
                               error=error,
                               reason=error_reason,
                               description=error_description), 400

    code = request.args.get('code')
    if not code:
        return render_template('ig_error.html',
                               error='missing_code',
                               reason='No authorization code',
                               description='Instagram did not return an authorization code.'), 400

    # Step 1: Exchange code for short-lived access token
    token_data = _exchange_code_for_token(code)
    if 'error' in token_data:
        return render_template('ig_error.html',
                               error='token_exchange_failed',
                               reason='Token exchange failed',
                               description=token_data.get('error_message', str(token_data))), 400

    short_lived_token = token_data.get('access_token')
    ig_user_id = str(token_data.get('user_id'))

    # Step 2: Exchange for long-lived token (60 days)
    long_lived_data = _exchange_for_long_lived_token(short_lived_token)
    if 'error' in long_lived_data:
        # Fallback to short-lived token if exchange fails
        access_token = short_lived_token
        expires_at = datetime.utcnow() + timedelta(hours=1)
    else:
        access_token = long_lived_data.get('access_token', short_lived_token)
        expires_in = long_lived_data.get('expires_in', 5184000)  # Default 60 days
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Step 3: Fetch user profile info
    profile = _fetch_user_profile(access_token)
    username = profile.get('username', '')
    account_type = profile.get('account_type', '')
    profile_picture_url = profile.get('profile_picture_url', '')

    # Step 4: Store or update user in database
    user = User.query.filter_by(ig_user_id=ig_user_id).first()
    if user:
        user.access_token = access_token
        user.token_expires_at = expires_at
        user.ig_username = username or user.ig_username
        user.profile_picture_url = profile_picture_url or user.profile_picture_url
        user.account_type = account_type or user.account_type
        user.is_active = True
        user.updated_at = datetime.utcnow()
    else:
        user = User(
            ig_user_id=ig_user_id,
            ig_username=username,
            access_token=access_token,
            token_expires_at=expires_at,
            profile_picture_url=profile_picture_url,
            account_type=account_type
        )
        db.session.add(user)

    db.session.commit()

    # Store user ID in session for dashboard access
    session['ig_user_id'] = user.id

    return redirect(url_for('instagram_automation.dashboard_home'))


@ig_bp.route('/auth/disconnect')
def auth_disconnect():
    """Disconnect the Instagram account."""
    user_id = session.get('ig_user_id')
    if user_id:
        user = User.query.get(user_id)
        if user:
            user.is_active = False
            db.session.commit()
        session.pop('ig_user_id', None)

    return redirect(url_for('instagram_automation.login_page'))


@ig_bp.route('/auth/refresh-token')
def auth_refresh_token():
    """Manually refresh the long-lived token."""
    user_id = session.get('ig_user_id')
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    result = refresh_user_token(user)
    if result.get('success'):
        return jsonify({
            "success": True,
            "expires_at": user.token_expires_at.isoformat(),
            "days_remaining": user.token_days_remaining()
        })
    else:
        return jsonify({"error": result.get('error', 'Unknown error')}), 500


def refresh_user_token(user):
    """Refresh a user's long-lived token. Returns dict with success/error."""
    try:
        resp = requests.get(
            f"{Config.IG_GRAPH_URL}/refresh_access_token",
            params={
                "grant_type": "ig_refresh_token",
                "access_token": user.access_token
            },
            timeout=10
        )
        data = resp.json()

        if 'access_token' in data:
            user.access_token = data['access_token']
            expires_in = data.get('expires_in', 5184000)
            user.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            user.updated_at = datetime.utcnow()
            db.session.commit()
            print(f"✅ Token refreshed for @{user.ig_username}, expires in {user.token_days_remaining()} days")
            return {"success": True}
        else:
            error_msg = data.get('error', {}).get('message', str(data))
            print(f"❌ Token refresh failed for @{user.ig_username}: {error_msg}")
            return {"error": error_msg}

    except Exception as e:
        print(f"❌ Token refresh exception for @{user.ig_username}: {e}")
        return {"error": str(e)}


def get_current_user():
    """Get the currently logged-in user from session."""
    user_id = session.get('ig_user_id')
    if not user_id:
        return None
    return User.query.get(user_id)


# ============ Internal helpers ============

def _exchange_code_for_token(code):
    """Exchange authorization code for a short-lived access token."""
    try:
        resp = requests.post(Config.IG_TOKEN_URL, data={
            'client_id': Config.META_APP_ID,
            'client_secret': Config.META_APP_SECRET,
            'grant_type': 'authorization_code',
            'redirect_uri': Config.get_oauth_redirect_uri(),
            'code': code
        }, timeout=10)
        return resp.json()
    except Exception as e:
        return {"error": "request_failed", "error_message": str(e)}


def _exchange_for_long_lived_token(short_lived_token):
    """Exchange a short-lived token for a long-lived one (60 days)."""
    try:
        resp = requests.get(
            f"{Config.IG_GRAPH_URL}/access_token",
            params={
                'grant_type': 'ig_exchange_token',
                'client_secret': Config.META_APP_SECRET,
                'access_token': short_lived_token
            },
            timeout=10
        )
        return resp.json()
    except Exception as e:
        return {"error": "request_failed", "error_message": str(e)}


def _fetch_user_profile(access_token):
    """Fetch the Instagram user's profile info."""
    try:
        resp = requests.get(
            f"{Config.IG_GRAPH_URL}/me",
            params={
                'fields': 'user_id,username,account_type,profile_picture_url',
                'access_token': access_token
            },
            timeout=10
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e)}
