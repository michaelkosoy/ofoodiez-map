from flask import Flask, jsonify, render_template, request, redirect, url_for, session, Response
import pandas as pd
import os
import json
import time
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from geopy.geocoders import GoogleV3
from geopy.exc import GeocoderTimedOut
from dotenv import load_dotenv
import requests
from io import StringIO
from data import data as home_data
from database.models import PopupEvent, HappyHourPlace, HitechEmail
from instagram_automation.models import User
from instagram_automation.config import Config

# Load environment variables from .env file (for local development)
load_dotenv()

app = Flask(__name__, 
            static_url_path='/static',
            static_folder='app/static',
            template_folder='app/templates')

# Secret key for session management (used by Instagram automation OAuth)
app.secret_key = os.environ.get('SECRET_KEY', 'ofoodiez-dev-secret-change-in-prod')

# Database config for Instagram automation (supports Render postgres:// to postgresql:// conversion)
_db_url = os.environ.get('IG_DATABASE_URL') or os.environ.get('DATABASE_URL')
if _db_url:
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instagram_automation.db'

# Connection-pool hardening for the shared SQLAlchemy engine. Must be set BEFORE
# init_ig_automation (which calls db.init_app): pool_pre_ping avoids stale
# Supabase pooler connections after idle periods, pool_recycle refreshes them.
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 1800,
}


# Register Instagram Automation blueprint
from instagram_automation import init_app as init_ig_automation
init_ig_automation(app)

# The WhatsApp referral bot now runs as its OWN Render service (wa_wsgi:app) —
# see docs/whatsapp-bot-standalone-service-plan.md. It is intentionally NOT
# mounted here, so this service is purely the map/site.

# Register Admin blueprint
from admin import admin_bp
app.register_blueprint(admin_bp)

# Register site member accounts (registration/login + Google SSO + gated Services)
from accounts import accounts_bp, current_user
app.register_blueprint(accounts_bp)


@app.context_processor
def _inject_current_user():
    """Expose the logged-in member to every template (top-bar account widget)."""
    return {'current_user': current_user()}


# Register PayPlus billing (Subscribe -> hosted checkout -> signed callback)
from billing import billing_bp
app.register_blueprint(billing_bp)

# Register the AI CV reviewer (/hitech/cv-review, graded against app/data/cv_guide_full.md)
from cv_review import cv_review_bp
app.register_blueprint(cv_review_bp)

# Start Telegram bot in a background thread
import threading
from telegram_bot.bot import run_bot

# Only start the bot in the main thread if reloading or if not in debug mode
is_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
if not app.debug or is_reloader:
    bot_thread = threading.Thread(target=run_bot, args=(app,), daemon=True)
    bot_thread.start()
    print("🚀 Started Telegram bot background thread.")

# Helper to get env var or use default if missing/placeholder
def get_env_var(name, default=None):
    val = os.environ.get(name)
    if not val or val.startswith('your_'):
        return default
    return val

# API Key from environment variable
GOOGLE_MAPS_API_KEY = get_env_var('GOOGLE_MAPS_API_KEY')

if not GOOGLE_MAPS_API_KEY:
    raise ValueError("GOOGLE_MAPS_API_KEY environment variable is not set correctly in .env")

# Google Sheets URL (converted to CSV export)
SHEET_ID = get_env_var('SHEET_ID', '1yvXOS3l_0Wr0SxLf9YZE8RaFzwgQop4MshD5pbtmwzA')
SHEET_URL = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv'

# Cache configuration
CACHE_DIR = 'data'
GEOCODE_CACHE_FILE = os.path.join(CACHE_DIR, 'geocode_cache.json')
CACHE_EXPIRY_HOURS = 24

# Initialize geolocator
geolocator = GoogleV3(api_key=GOOGLE_MAPS_API_KEY, user_agent="ofoodiez_map")


# ============ GEOCODE CACHE (Persistent - stored in git) ============

def load_geocode_cache():
    """Load geocode cache from file."""
    if os.path.exists(GEOCODE_CACHE_FILE):
        try:
            with open(GEOCODE_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Could not load geocode cache: {e}")
    return {}

def save_geocode_cache(cache):
    """Save geocode cache to file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(GEOCODE_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Could not save geocode cache: {e}")

# Load geocode cache on startup
geocode_cache = load_geocode_cache()
print(f"📍 Loaded {len(geocode_cache)} cached geocodes")

def geocode_address(address, city=""):
    """Geocode an address to get latitude and longitude."""
    global geocode_cache
    
    if not address:
        return None, None
    
    # Build full address with Israel for better accuracy
    if city:
        full_address = f"{address}, {city}, Israel"
    else:
        full_address = f"{address}, Israel"
    
    # Check cache first
    if full_address in geocode_cache:
        cached = geocode_cache[full_address]
        if cached and len(cached) == 2:
            return cached[0], cached[1]
        return None, None
    
    try:
        location = geolocator.geocode(full_address)
        if location:
            result = [location.latitude, location.longitude]
            geocode_cache[full_address] = result
            save_geocode_cache(geocode_cache)
            print(f"  📍 Geocoded: {full_address} -> {result}")
            return result[0], result[1]
    except GeocoderTimedOut:
        print(f"  ⚠️ Geocoding timeout for: {full_address}")
    except Exception as e:
        print(f"  ⚠️ Geocoding error for {full_address}: {e}")
    
    geocode_cache[full_address] = None
    save_geocode_cache(geocode_cache)
    return None, None


# ============ DATA CACHE (In-memory with TTL) ============

# In-memory cache for places data
_data_cache = {
    'places': None,
    'timestamp': None
}

def get_cached_data():
    """Get cached data if not expired."""
    if _data_cache['places'] is None or _data_cache['timestamp'] is None:
        return None
    
    # Check expiry
    if datetime.now() - _data_cache['timestamp'] < timedelta(hours=CACHE_EXPIRY_HOURS):
        hours_remaining = CACHE_EXPIRY_HOURS - (datetime.now() - _data_cache['timestamp']).seconds // 3600
        print(f"✓ Using cached data (expires in ~{hours_remaining} hours)")
        return _data_cache['places']
    
    print("⏰ Data cache expired, fetching fresh data...")
    return None

def set_cached_data(places):
    """Cache places data in memory."""
    _data_cache['places'] = places
    _data_cache['timestamp'] = datetime.now()
    print(f"💾 Cached {len(places)} places in memory")

def clear_data_cache():
    """Clear the in-memory data cache."""
    _data_cache['places'] = None
    _data_cache['timestamp'] = None
    print("🗑️ Data cache cleared")

def get_last_update():
    """Get the last update date from the database, fallback to config file."""
    try:
        from database.models import HappyHourPlace
        # Get the latest updated_at from the database
        latest_place = HappyHourPlace.query.order_by(HappyHourPlace.updated_at.desc()).first()
        if latest_place and latest_place.updated_at:
            return latest_place.updated_at.strftime("%d-%m-%Y")
    except Exception as e:
        print(f"⚠️ Could not fetch last update from DB: {e}")

    config_file = os.path.join(CACHE_DIR, 'config.json')
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                date_str = config.get('last_update', '')
                if date_str:
                    # Convert YYYY-MM-DD to DD-MM-YYYY
                    parts = date_str.split('-')
                    if len(parts) == 3:
                        return f"{parts[2]}-{parts[1]}-{parts[0]}"
        return ''
    except:
        return ''

# ============ ROUTES ============

@app.route('/')
def home():
    """Render the new homepage with data."""
    # Load popups from Supabase instead of mock data
    try:
        db_events = PopupEvent.query.order_by(PopupEvent.date.asc()).all()
        popups_list = [event.to_dict() for event in db_events]

        # Dynamically inject into a copy of home_data
        data_to_render = dict(home_data)
        data_to_render['popups'] = popups_list
    except Exception as e:
        print(f"⚠️ Error fetching popups from database: {e}")
        data_to_render = home_data # Fallback to mock data in case of db errors
        
    return render_template('home.html', data=data_to_render)

def _load_blog(slug):
    path = os.path.join(os.path.dirname(__file__), 'app', 'data', f'blog_{slug}.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


@app.route('/accessibility')
def accessibility_statement():
    """הצהרת נגישות — required by the IL accessibility regulations (IS 5568);
    linked from the accessibility menu present on every page."""
    return render_template('accessibility.html')


@app.route('/blog/japan')
def blog_japan():
    """Japan travel & food guide — open to everyone for now.

    ponytail: the Grow paywall + landing/sales page (blog_japan_landing.html) are
    kept in place but unused while the guide is open; to re-gate, restore the
    has_item/GROW_ITEMS check that used to live here (see git history)."""
    return render_template('blog_japan.html', api_key=GOOGLE_MAPS_API_KEY,
                           c=_load_blog('japan'))

@app.route('/blog/instagram')
def blog_instagram():
    return render_template('blog_instagram.html')

@app.route('/blog/<category>')
def blog_category(category):
    return redirect('/', 302)

@app.route('/map')
def map_page():
    """Happy Hour Map page."""
    last_update = get_last_update()
    return render_template('index.html', api_key=GOOGLE_MAPS_API_KEY, last_update=last_update)

@app.route('/blog/bachelorette')
def bachelorette_page():
    from listing_submissions import get_config, filter_approved
    listing_config = get_config('bachelorette')
    bachelorette_data = _load_blog('bachelorette')
    bachelorette_data = filter_approved(bachelorette_data, listing_config)
    return render_template('bachelorette.html', bachelorette_data=bachelorette_data, data=home_data,
                           listing_slug='bachelorette', listing_config=listing_config)

@app.route('/bachelorette')
def bachelorette_redirect():
    return redirect('/blog/bachelorette', 301)

@app.route('/about')
def about_page():
    """About Me page."""
    return render_template('about.html', data=home_data)


@app.route('/portfolio')
def portfolio_page():
    """Employer Branding & Founder-Led Content Studio portfolio."""
    content = _load_portfolio_content()
    return render_template('portfolio.html', c=content.get('portfolio', {}))


def _load_portfolio_content():
    """Load portfolio content from portfolio_content.json."""
    path = os.path.join(os.path.dirname(__file__), 'app', 'data', 'portfolio_content.json')
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _load_hitech_data(filename):
    """Load a JSON data file from app/data/ for HiTech pages."""
    path = os.path.join(os.path.dirname(__file__), 'app', 'data', filename)
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _load_hitech_content():
    """Load the full static content translations and copy from hitech_content.json."""
    path = os.path.join(os.path.dirname(__file__), 'app', 'data', 'hitech_content.json')
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


@app.route('/hitech')
def hitech_page():
    """HiTech hub home page — hero + feature cards + companies carousel."""
    companies = _load_hitech_data('hitech_companies.json')
    content = _load_hitech_content()
    return render_template('hitech.html', active_hitech_page='home', active_page='hitech', companies=companies, c=content.get('hitech', {}))


@app.route('/hitech/community')
def hitech_community():
    """HiTech community waitlist page."""
    content = _load_hitech_content()
    return render_template('hitech_community.html', active_hitech_page='community', active_page='hitech', c=content.get('community', {}))


# ── /hitech/referrals-bot companies list ─────────────────────────────────────
# The live wa_companies⋈wa_advocates query runs ~8s in prod (deterministic — a
# DB-side issue) and the list changes only on rare admin edits, so we serve it
# from an in-process cache. Stale reads refresh in the background, so a page view
# never waits on the slow query; the cache is warmed at startup below.
# ponytail: TTL + serve-stale. If admin edits must show instantly, bust the cache
# from the advocate/company write endpoints instead of shortening the TTL.
_FEATURED_NAMES = {'google', 'meta', 'microsoft', 'amazon', 'apple', 'wix',
                   'monday.com', 'fiverr', 'checkout.com', 'taboola'}
_BOT_COMPANIES = {"data": None, "ts": 0.0, "refreshing": False}
_BOT_COMPANIES_TTL = 600  # seconds


def _refresh_bot_companies():
    """Query companies that have an active advocate and repopulate the cache."""
    from whatsapp_bot.models import WaCompany, WaAdvocate
    try:
        with app.app_context():
            t0 = time.monotonic()
            rows = (WaCompany.query
                    .join(WaAdvocate, WaCompany.id == WaAdvocate.company_id)
                    .filter(WaAdvocate.status == 'active')
                    .distinct()
                    .order_by(WaCompany.name.asc())
                    .all())
            data = [{"name": co.name,
                     # careers_url set in admin (WhatsApp → Companies → Edit); None → non-clickable card.
                     "careers_url": co.careers_url,
                     "featured": co.name.lower() in _FEATURED_NAMES} for co in rows]
        print(f"⏱️  referrals-bot companies query: {time.monotonic() - t0:.2f}s ({len(data)} companies)")
        _BOT_COMPANIES["data"] = data
        _BOT_COMPANIES["ts"] = time.monotonic()
    except Exception as e:
        print(f"⚠️ Error fetching companies with advocates: {e}")
    finally:
        _BOT_COMPANIES["refreshing"] = False


def _companies_with_advocates():
    """Cached companies list for the bot page — instant read, background refresh."""
    fresh = (_BOT_COMPANIES["data"] is not None
             and time.monotonic() - _BOT_COMPANIES["ts"] < _BOT_COMPANIES_TTL)
    if not fresh and not _BOT_COMPANIES["refreshing"]:
        _BOT_COMPANIES["refreshing"] = True
        if _BOT_COMPANIES["data"] is None:
            _refresh_bot_companies()                                              # first load: block once
        else:
            threading.Thread(target=_refresh_bot_companies, daemon=True).start()  # serve stale, refresh async
    return _BOT_COMPANIES["data"] or []


# Warm the cache off the request path so the first visitor doesn't eat the query.
threading.Thread(target=_refresh_bot_companies, daemon=True).start()


@app.route('/hitech/referrals-bot')
def hitech_bot():
    """HiTech referrals bot info + advocates directory. The companies list is
    cached and refreshed in the background — see _companies_with_advocates()."""
    content = _load_hitech_content()
    return render_template('hitech_bot.html', active_hitech_page='referrals-bot',
                           active_page='hitech', companies=_companies_with_advocates(),
                           c=content.get('bot', {}))


@app.route('/hitech/cv-guide')
def hitech_cv():
    """HiTech interactive CV guide."""
    content = _load_hitech_content()
    return render_template('hitech_cv.html', active_hitech_page='cv-guide', active_page='hitech', c=content.get('cv', {}))


@app.route('/hitech/cv-guide/full', methods=['GET', 'POST'])
def hitech_cv_full():
    """Full Job Search & CV guide (Hebrew), served from app/data/cv_guide_full.md —
    open to everyone for now.

    ponytail: the shared password gate below is kept in place but unused while the
    guide is open; to re-enable, make guide_md conditional on
    session.get('cv_guide_unlocked') again (or swap for billing.item_gate like
    /blog/japan used to do).
    """
    error = False
    if request.method == 'POST':
        if request.form.get('password', '').strip() == os.environ.get('CV_GUIDE_PASSWORD', '123456'):
            session['cv_guide_unlocked'] = True
            return redirect(url_for('hitech_cv_full'))
        error = True
    path = os.path.join(os.path.dirname(__file__), 'app', 'data', 'cv_guide_full.md')
    with open(path, encoding='utf-8') as f:
        guide_md = f.read()
    return render_template('hitech_cv_full.html', active_hitech_page='cv-guide',
                           active_page='hitech', guide_md=guide_md, error=error)


@app.route('/hitech/unsubscribe')
def hitech_unsubscribe():
    """Unsubscribe a user from the HiTech community waitlist."""
    email = request.args.get('email', '').strip().lower()
    if not email:
        return render_template('hitech_unsubscribed.html', email='Unknown')

    try:
        from database.models import db
        entry = HitechEmail.query.filter_by(email=email).first()
        if entry:
            db.session.delete(entry)
            db.session.commit()

        # Notify ops/admin
        from whatsapp_bot.emailer import send_custom_community_email
        ops_email = os.environ.get("WA_OPS_EMAIL") or "info@ofoodiez.com"
        send_custom_community_email(
            to_email=ops_email,
            subject=f"HiTech Unsubscribe: {email}",
            body_html=f"<div style='font-family: sans-serif; font-size: 15px; color: #222; direction: rtl; text-align: right;'>"
                      f"<p>התקבל ביקוש להסרה מרשימת התפוצה של קהילת ההייטק:</p>"
                      f"<p>כתובת המייל: <b>{email}</b></p>"
                      f"<p>המשתמש הוסר אוטומטית מבסיס הנתונים.</p>"
                      f"</div>",
            body_text=f"Request to unsubscribe received from: {email}\nThe email was automatically removed from the database."
        )
    except Exception as e:
        print(f"⚠️ Error during HiTech unsubscribe for {email}: {e}")

    return render_template('hitech_unsubscribed.html', email=email)


@app.route('/api/hitech/subscribe', methods=['POST'])
def hitech_subscribe():
    """Collect registration for the HiTech community waitlist."""
    data = request.get_json(silent=True) or {}
    email       = (data.get('email') or '').strip().lower()
    name        = (data.get('name') or '').strip()
    linkedin_url= (data.get('linkedin_url') or '').strip()
    job_title   = (data.get('job_title') or '').strip() or None
    company     = (data.get('company') or '').strip() or None

    if not email or '@' not in email:
        return jsonify({'success': False, 'message': 'Invalid email address.'}), 400

    from database.models import db as _db
    existing = HitechEmail.query.filter_by(email=email).first()
    if existing:
        return jsonify({'success': True, 'message': 'already_registered'})

    # Best-effort: scrape the LinkedIn job title if not provided by user
    if not job_title and linkedin_url:
        try:
            import re as _re
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
                ),
                'Accept-Language': 'en-US,en;q=0.9',
            }
            _url = linkedin_url if linkedin_url.startswith('http') else 'https://' + linkedin_url
            resp = requests.get(_url, headers=headers, timeout=6, allow_redirects=True)
            if resp.status_code == 200:
                m = _re.search(r'<title[^>]*>([^<]+)</title>', resp.text, _re.IGNORECASE)
                if m:
                    parts = [p.strip() for p in m.group(1).split(' - ')]
                    if len(parts) >= 2 and 'linkedin' not in parts[1].lower():
                        job_title = parts[1]
        except Exception:
            pass  # scraping is best-effort; never block signup

    entry = HitechEmail(
        email=email,
        name=name or None,
        linkedin_url=linkedin_url or None,
        job_title=job_title,
        company=company,
    )
    _db.session.add(entry)
    _db.session.commit()

    return jsonify({'success': True, 'message': 'subscribed'})


# ── Business listing submissions (generic, config-driven — see listing_submissions.py):
# per-IP rate limit. ponytail: in-memory dict — correct for the single gunicorn
# worker in the Procfile; move to flask-limiter/redis if --workers ever grows
# past 1. (Same pattern as cv_review.py's rate limiter.)
_LISTING_RATE_LIMIT = 5        # submissions…
_LISTING_RATE_WINDOW = 3600    # …per hour, per client IP
_listing_recent_submissions = {}  # ip -> [timestamps]


def _listing_client_ip():
    return (request.headers.get('CF-Connecting-IP')
            or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or request.remote_addr or 'unknown')


def _listing_rate_limited(ip):
    now = time.time()
    hits = [t for t in _listing_recent_submissions.get(ip, []) if now - t < _LISTING_RATE_WINDOW]
    if len(hits) >= _LISTING_RATE_LIMIT:
        _listing_recent_submissions[ip] = hits
        return True
    hits.append(now)
    _listing_recent_submissions[ip] = hits
    if len(_listing_recent_submissions) > 10000:  # crude memory guard
        _listing_recent_submissions.clear()
    return False


@app.route('/api/<slug>/submit-business', methods=['POST'])
def submit_business_listing(slug):
    """Public 'add your business' form for any configured blog listing page
    (see listing_submissions.LISTING_SUBMISSION_CONFIGS). Lands as a pending
    entry directly in the matching array of blog_<slug>.json, filtered out of
    the public page until an admin approves it."""
    from listing_submissions import get_config, blog_json_path, atomic_write_json

    config = get_config(slug)
    if not config:
        return jsonify({'success': False, 'message': 'Unknown listing page.'}), 404

    data = request.get_json(silent=True) or {}

    # Honeypot: real users never see/fill this field, bots often do.
    if (data.get('website') or '').strip():
        return jsonify({'success': True})

    ip = _listing_client_ip()
    if _listing_rate_limited(ip):
        return jsonify({'success': False, 'message': 'Too many submissions, please try again later.'}), 429

    kind = (data.get('kind') or '').strip()
    name = (data.get('name') or '').strip()
    contact_email = (data.get('contact_email') or '').strip()
    contact_phone = (data.get('contact_phone') or '').strip()

    if kind not in config['kinds']:
        return jsonify({'success': False, 'message': 'Invalid submission type.'}), 400
    if not name:
        return jsonify({'success': False, 'message': 'Business name is required.'}), 400
    if not contact_email and not contact_phone:
        return jsonify({'success': False, 'message': 'Please provide an email or phone number so we can reach you.'}), 400

    entry = {
        'submission_id': secrets.token_hex(5),
        'status': 'pending',
        'name': name,
        'category': (data.get('category') or '').strip(),
        'description': (data.get('description') or '').strip(),
        'location': (data.get('location') or '').strip(),
        'price': (data.get('price') or '').strip(),
        'discount': (data.get('discount') or '').strip(),
        'link': (data.get('link') or '').strip(),
        'link_text': (data.get('link_text') or '').strip(),
        'instagram': (data.get('instagram') or '').strip(),
        'whatsapp': (data.get('whatsapp') or '').strip(),
        'contact_name': (data.get('contact_name') or '').strip(),
        'contact_email': contact_email,
        'contact_phone': contact_phone,
        'submitted_at': datetime.utcnow().isoformat(),
    }

    path = blog_json_path(slug)
    with open(path, encoding='utf-8') as f:
        blog_data = json.load(f)
    array_key = config['kinds'][kind]['array_key']
    blog_data.setdefault(array_key, []).append(entry)
    atomic_write_json(path, blog_data)

    try:
        from whatsapp_bot.emailer import send_custom_community_email
        ops_email = os.environ.get("WA_OPS_EMAIL") or "info@ofoodiez.com"
        kind_label = config['kinds'][kind]['label_he']
        listing_title = config['listing_title_he']
        send_custom_community_email(
            to_email=ops_email,
            subject=f"הגשת עסק חדשה ל{listing_title}: {name}",
            body_html=(
                "<div style='font-family: sans-serif; font-size: 15px; color: #222; direction: rtl; text-align: right;'>"
                f"<p>התקבלה הגשה חדשה ({kind_label}) ל{listing_title}, ממתינה לאישור:</p>"
                f"<p><b>שם:</b> {name}<br>"
                f"<b>קטגוריה:</b> {entry['category']}<br>"
                f"<b>הנחה מוצעת:</b> {entry['discount'] or '-'}<br>"
                f"<b>איש קשר:</b> {entry['contact_name'] or '-'}<br>"
                f"<b>אימייל:</b> {contact_email or '-'}<br>"
                f"<b>טלפון:</b> {contact_phone or '-'}</p>"
                "<p>לאישור/דחייה: כנסו לפאנל הניהול.</p>"
                "</div>"
            ),
            body_text=(
                f"New {kind} submission for {listing_title}, pending approval:\n"
                f"Name: {name}\nCategory: {entry['category']}\nDiscount offered: {entry['discount'] or '-'}\n"
                f"Contact: {entry['contact_name'] or '-'} / {contact_email or '-'} / {contact_phone or '-'}\n"
                "Review it in the admin panel."
            ),
        )
    except Exception as e:
        print(f"⚠️ Error sending {slug} submission notification: {e}")

    return jsonify({'success': True})


@app.route('/privacy')
def privacy_policy():
    """Privacy Policy for Meta App Review."""
    return render_template('legal/privacy.html')

@app.route('/terms')
def terms_of_service():
    """Terms of Service for Meta App Review."""
    return render_template('legal/terms.html')

@app.route('/data-deletion')
def data_deletion():
    """Data Deletion Instructions for Meta App Review."""
    return render_template('legal/data_deletion.html')


@app.route('/health')
def health_check():
    return "OK", 200

# ============ SEO ============
SITE_URL = 'https://ofoodiez.com'
SITEMAP_PAGES = ['/', '/map', '/about', '/blog/japan', '/blog/bachelorette',
                 '/blog/instagram', '/hitech', '/hitech/community',
                 '/hitech/referrals-bot', '/hitech/cv-guide']

@app.route('/robots.txt')
def robots_txt():
    # HTML pages we don't want indexed carry <meta name="robots" content="noindex">
    # instead of a Disallow here, so crawlers can actually see the noindex.
    lines = ['User-agent: *',
             'Disallow: /admin/',
             # Googlebot renders JS: it must fetch the endpoints that feed the
             # map and Instagram pages, so those two stay crawlable.
             'Allow: /api/places',
             'Allow: /api/instagram/',
             'Disallow: /api/',
             'Disallow: /pay/',
             'Disallow: /paid/',
             'Disallow: /billing/',
             'Disallow: /webhooks/',
             'Disallow: /auth/',
             'Allow: /',
             '',
             f'Sitemap: {SITE_URL}/sitemap.xml']
    return Response('\n'.join(lines) + '\n', mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    urls = '\n'.join(f'  <url><loc>{SITE_URL}{p}</loc></url>' for p in SITEMAP_PAGES)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f'{urls}\n</urlset>\n')
    return Response(xml, mimetype='application/xml')

# ============ INSTAGRAM FEED API ============
IG_POSTS_CACHE_FILE = os.path.join(CACHE_DIR, 'ig_posts_cache.json')
IG_CACHE_EXPIRY_HOURS = 1

def fetch_all_ig_posts():
    """Fetch all IG posts for the active user, using pagination. Cache results."""
    # Check cache first
    if os.path.exists(IG_POSTS_CACHE_FILE):
        file_mod_time = datetime.fromtimestamp(os.path.getmtime(IG_POSTS_CACHE_FILE))
        if datetime.now() - file_mod_time < timedelta(hours=IG_CACHE_EXPIRY_HOURS):
            try:
                with open(IG_POSTS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading IG posts cache: {e}")
                
    # Needs fetching. Get active user
    try:
        # Force the backend to ONLY fetch posts for the official ofoodiez account
        # This prevents random users from showing their posts if they somehow connected their account
        user = User.query.filter_by(ig_username='ofoodiez', is_active=True).first()
        
        # Fallback to the tester account if we are developing locally
        if not user:
            user = User.query.filter_by(ig_username='tester_account', is_active=True).first()
            
        if not user or not user.access_token:
            return []

        # If user is a mock account, return mock posts for testing
        if user.access_token == 'test_token_123' or user.ig_username == 'tester_account':
            print("🧪 Using mock Instagram posts for testing account")
            mock_posts = []
            for i in range(1, 26):
                mock_posts.append({
                    "id": f"mock_post_{i}",
                    "caption": f"This is a mock Instagram post #{i}! Finding the best places in Tel Aviv like a delicious Pizza or amazing Sushi. #ofoodiez",
                    "media_url": "https://images.unsplash.com/photo-1544148103-0773bf10d330?q=80&w=600&auto=format&fit=crop",
                    "permalink": "https://instagram.com/ofoodiez",
                    "media_type": "IMAGE",
                    "timestamp": (datetime.now() - timedelta(days=i)).isoformat()
                })
            # Add some specific keywords for search testing
            mock_posts[0]["caption"] = "Just found the best Burger in town! #foodie"
            mock_posts[1]["caption"] = "Amazing sushi rolls for dinner 🍣 #sushi"
            mock_posts[2]["caption"] = "Nothing beats a good Pasta on a rainy day."
            mock_posts[2]["media_type"] = "VIDEO"
            mock_posts[2]["thumbnail_url"] = "https://images.unsplash.com/photo-1473093295043-cdd812d0e601?q=80&w=600&auto=format&fit=crop"
            return mock_posts

        posts = []
        url = f"{Config.IG_GRAPH_URL}/{Config.GRAPH_API_VERSION}/{user.ig_user_id}/media"
        params = {
            'fields': 'id,caption,media_url,permalink,media_type,media_product_type,thumbnail_url,timestamp,like_count,comments_count,is_shared_to_feed',
            'access_token': user.access_token,
            'limit': 100
        }
        
        while url:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            if 'data' in data:
                for post in data['data']:
                    # Filter out Reels that were NOT shared to the main feed grid
                    if post.get('media_product_type') == 'REELS' and post.get('is_shared_to_feed') is False:
                        continue
                    posts.append(post)
            
            # Pagination
            paging = data.get('paging', {})
            url = paging.get('next')
            params = {} # The next URL already contains all parameters including access_token
            
            # Guard against fetching too many posts to prevent timeouts
            if len(posts) >= 500:
                break
                
        # Save to cache
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(IG_POSTS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(posts, f, ensure_ascii=False)
            
        print(f"📸 Fetched and cached {len(posts)} Instagram posts")
        return posts
    except Exception as e:
        print(f"❌ Error fetching IG posts from API: {e}")
        # Fallback to expired cache if available
        if os.path.exists(IG_POSTS_CACHE_FILE):
            try:
                with open(IG_POSTS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return []

@app.route('/api/instagram/posts')
def api_ig_posts():
    """Returns paginated posts"""
    limit = int(request.args.get('limit', 12))
    offset = int(request.args.get('offset', 0))
    posts = fetch_all_ig_posts()
    
    paginated = posts[offset:offset+limit]
    has_more = len(posts) > offset + limit
    
    return jsonify({
        "posts": paginated,
        "has_more": has_more
    })

@app.route('/api/instagram/search')
def api_ig_search():
    """Searches across all posts by caption text"""
    query = request.args.get('q', '').lower().strip()
    limit = int(request.args.get('limit', 12))
    offset = int(request.args.get('offset', 0))
    posts = fetch_all_ig_posts()
    
    if not query:
        paginated = posts[offset:offset+limit]
        has_more = len(posts) > offset + limit
        return jsonify({"posts": paginated, "has_more": has_more})
        
    filtered = []
    for p in posts:
        caption = p.get('caption', '').lower()
        if query in caption:
            filtered.append(p)
            
    paginated = filtered[offset:offset+limit]
    has_more = len(filtered) > offset + limit
    return jsonify({"posts": paginated, "has_more": has_more})

@app.route('/api/places')
def get_places():
    try:
        # Check in-memory cache first
        cached_places = get_cached_data()
        if cached_places:
            return jsonify(cached_places)
        
        # Try fetching from DB first
        try:
            db_places = HappyHourPlace.query.all()
            if db_places:
                places_list = [p.to_dict() for p in db_places]
                
                # Geocode addresses if Latitude/Longitude are missing
                for place in places_list:
                    has_lat = place.get('Latitude') is not None and place.get('Latitude') != ""
                    has_lng = place.get('Longitude') is not None and place.get('Longitude') != ""
                    
                    if not has_lat or not has_lng:
                        address = place.get('Address', '')
                        city = place.get('City', '')
                        if address:
                            lat, lng = geocode_address(address, city)
                            if lat and lng:
                                place['Latitude'] = lat
                                place['Longitude'] = lng

                set_cached_data(places_list)
                print(f"✓ Loaded {len(places_list)} places from Database")
                return jsonify(places_list)
            else:
                print("⚠️ Database is empty. Falling back to Google Sheets...")
        except Exception as db_err:
            print(f"⚠️ Database fetch failed: {db_err}. Falling back to Google Sheets...")
        
        # Fallback: Fetch fresh data from Google Sheets
        try:
            # Try to bypass system proxies if they are causing issues
            response = requests.get(SHEET_URL, timeout=10, proxies={'http': None, 'https': None})
            response.raise_for_status()
            df = pd.read_csv(StringIO(response.content.decode('utf-8')))
            print("✓ Loaded fresh data from Google Sheets")
        except Exception as e:
            print(f"⚠️ Could not fetch from Google Sheets: {e}")
            # Fallback to local cache file if network fetch fails
            cache_file = os.path.join(CACHE_DIR, 'places_cache.json')
            if os.path.exists(cache_file):
                print(f"🔄 Falling back to local cache: {cache_file}")
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return jsonify(json.load(f))
            else:
                # If no sheets and no cache, then we re-raise to show the error
                raise e
        print(f"  Columns: {list(df.columns)}")
        
        # Strip whitespace from column names
        df.columns = df.columns.str.strip()
        
        # Map Google Sheets column names to expected frontend column names
        column_mapping = {
            'Place Name (English)': 'Name',
            'Place Name (Hebrew)': 'NameHebrew',
            'Instagram Link': 'InstagramURL',
            'Category': 'Category',
            'Description': 'Description',
            'Address': 'Address',
            'City': 'City',
            'Google Maps Link': 'GoogleMapsLink',
            'Reservation Link': 'ReservationLink',
            'OpeningHours': 'OpeningHours',
            'Latitude': 'Latitude',
            'Longitude': 'Longitude',
            'Recommended': 'Recommended',
            'Sunday': 'Sunday',
            'Monday': 'Monday',
            'Tuesday': 'Tuesday',
            'Wednesday': 'Wednesday',
            'Thursday': 'Thursday',
            'Friday': 'Friday',
            'Saturday': 'Saturday',
            'Verified': 'Verified',
            'Kosher': 'Kosher'
        }
        
        # Drop duplicate columns (keep the first one)
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Drop the InstagramURL column if it exists (we only use Instagram Link)
        if 'InstagramURL' in df.columns:
            df = df.drop(columns=['InstagramURL'])
        
        # Rename columns that exist in the mapping
        df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})
        
        # Fill NaN values with empty string to avoid JSON errors (Fixes SyntaxError: Unexpected token 'N')
        df = df.fillna("")
        
        # Strip whitespace from all string columns (fixes "After 20:00 " issue)
        df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        
        # Filter out rows where Name is empty (if Name column exists)
        if 'Name' in df.columns:
            df = df[df['Name'].str.strip().astype(bool)]

        # Filter out rows where Category is empty (if Category column exists)
        if 'Category' in df.columns:
            df = df[df['Category'].str.strip().astype(bool)]

        # Normalize Kosher to boolean
        if 'Kosher' in df.columns:
            df['Kosher'] = df['Kosher'].apply(
                lambda v: True if str(v).strip().lower() in ('true', 'yes', '1') else False
            )

        # Geocode addresses if Latitude/Longitude are missing
        places = df.to_dict(orient='records')
        for place in places:
            # Check if coordinates are missing or empty
            has_lat = place.get('Latitude') and place.get('Latitude') != ""
            has_lng = place.get('Longitude') and place.get('Longitude') != ""
            
            if not has_lat or not has_lng:
                # Try to geocode from address
                address = place.get('Address', '')
                city = place.get('City', '')
                lat, lng = geocode_address(address, city)
                if lat and lng:
                    place['Latitude'] = lat
                    place['Longitude'] = lng
        
        # Save to in-memory cache
        set_cached_data(places)
        
        return jsonify(places)
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/refresh')
def refresh_cache():
    """Force refresh the data cache."""
    # Simple security check
    key = request.args.get('key')
    admin_secret = get_env_var('ADMIN_SECRET', 'ofoodiez2025') # Default secret
    
    if key != admin_secret:
        return jsonify({"error": "Unauthorized"}), 401

    clear_data_cache()
    
    # Trigger a fetch to ensure data is valid and update the cache immediately
    try:
        # We call the internal logic or just call get_places (which handles fetching)
        # However, get_places returns a Response object (jsonify), so we shouldn't call it directly if we want the data.
        # But for populating the cache, it's fine.
        # Better: just clear cache and let the next request handle it, OR fetch it here to confirm success.
        # Let's fetch it here to be sure.
        
        # Re-using the logic from get_places would be best if it was refactored, 
        # but calling the route function is okay-ish or we can just return success.
        # Let's just return success to keep it simple and fast.
        return jsonify({
            "status": "Cache cleared successfully", 
            "message": "Next visit to the map will load fresh data.",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/update-date')
def update_date():
    """Update the last_update date in config.json to today."""
    # Simple security check
    key = request.args.get('key')
    admin_secret = get_env_var('ADMIN_SECRET', 'ofoodiez2025') # Default secret
    
    if key != admin_secret:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        config_file = os.path.join(CACHE_DIR, 'config.json')
        os.makedirs(CACHE_DIR, exist_ok=True)
        
        current_date = datetime.now().strftime("%Y-%m-%d")
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({'last_update': current_date}, f, indent=2)
            
        print(f"📅 Updated last_update to {current_date}")
        
        return jsonify({
            "status": "Date updated successfully",
            "last_update": current_date,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        print(f"⚠️ Could not update config.json: {e}")
        return jsonify({"error": str(e)}), 500

# Formspree configuration (free email API service)
# Get your form ID from https://formspree.io - create a free account and form
FORMSPREE_ENDPOINT = get_env_var('FORMSPREE_ENDPOINT', '')

@app.route('/api/submit-happy-hour', methods=['POST'])
def submit_happy_hour():
    """Receive happy hour submission and send via Formspree."""
    try:
        data = request.get_json()
        
        # Build formatted message
        days_str = ', '.join(data.get('days', [])) or 'Not specified'
        
        form_mode = data.get('formMode', 'new')
        is_update = form_mode == 'update'
        
        if is_update:
            message = f"""
🔄 Happy Hour UPDATE Request!

📍 Place to Update: {data.get('existingPlace', 'Not specified')}

📝 Requested Changes:
- Description: {data.get('description', '') or 'No change'}
- Category: {data.get('category', '') or 'No change'}
- Days: {days_str}
- Instagram: {data.get('instagram', '') or 'No change'}
- Reservation: {data.get('reservation', '') or 'No change'}

📌 Notes: {data.get('notes', '') or 'None'}

📅 Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
        else:
            message = f"""
🍻 New Happy Hour Submission!

📍 Place Details:
- Name (Hebrew): {data.get('placeNameHe', '')}
- Name (English): {data.get('placeNameEn', '')}
- Description: {data.get('description', '')}
- Address: {data.get('address', '')}
- City: {data.get('city', '')}
- Category: {data.get('category', '')}
- Days: {days_str}

🔗 Links:
- Instagram: {data.get('instagram', '') or 'Not provided'}
- Reservation: {data.get('reservation', '') or 'Not provided'}

📌 Notes: {data.get('notes', '') or 'None'}

📅 Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
        
        # Always save to file as backup
        submissions_file = os.path.join(CACHE_DIR, 'submissions.json')
        submissions = []
        if os.path.exists(submissions_file):
            try:
                with open(submissions_file, 'r', encoding='utf-8') as f:
                    submissions = json.load(f)
            except:
                pass
        
        data['submitted_at'] = datetime.now().isoformat()
        submissions.append(data)
        
        with open(submissions_file, 'w', encoding='utf-8') as f:
            json.dump(submissions, f, ensure_ascii=False, indent=2)
        
        # Send via Formspree if configured
        if FORMSPREE_ENDPOINT:
            formspree_data = {
                'email': 'ofir.lazarov@gmail.com',
                '_subject': f"🍻 New Happy Hour: {data.get('placeNameEn', 'Unknown')}",
                'message': message,
                'place_name_he': data.get('placeNameHe', ''),
                'place_name_en': data.get('placeNameEn', ''),
                'description': data.get('description', ''),
                'address': data.get('address', ''),
                'city': data.get('city', ''),
                'category': data.get('category', ''),
                'days': days_str,
                'instagram': data.get('instagram', ''),
                'reservation': data.get('reservation', '')
            }
            
            response = requests.post(
                FORMSPREE_ENDPOINT,
                json=formspree_data,
                headers={'Accept': 'application/json'}
            )
            
            if response.status_code == 200:
                print(f"✅ Email sent via Formspree for: {data.get('placeNameEn')}")
            else:
                print(f"⚠️ Formspree error: {response.status_code} - {response.text}")
        else:
            print("📧 Formspree not configured, submission saved to file only")
        
        return jsonify({"success": True, "message": "Submission received"})
        
    except Exception as e:
        print(f"❌ Error submitting happy hour: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
