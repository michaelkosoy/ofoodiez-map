from flask import Flask, jsonify, render_template, request
import pandas as pd
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from geopy.geocoders import GoogleV3
from geopy.exc import GeocoderTimedOut
from dotenv import load_dotenv
import requests
from io import StringIO
from data import data as home_data, bachelorette_data
from database.models import PopupEvent, HappyHourPlace
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

# Register WhatsApp referral-bot blueprint (after IG init: reuses the shared db,
# does not re-init the extension or call create_all — wa_ tables are created by
# the one-time Supabase SQL script; see docs/whatsapp-referral-bot-plan.md §4).
from whatsapp_bot import init_app as init_wa_bot
init_wa_bot(app)

# Register Admin blueprint
from admin import admin_bp
app.register_blueprint(admin_bp)

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
    """Get the last update date from config file."""
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

@app.route('/blog/<category>')
def blog_category(category):
    """Render specific blog category pages."""
    # Convert category slug to a title-case name (e.g. 'recipes' -> 'Recipes')
    category_title = category.replace('-', ' ').title()
    return render_template('blog_category.html', 
                           category_slug=category,
                           category_title=category_title,
                           data=home_data)

@app.route('/map')
def map_page():
    """Happy Hour Map page."""
    last_update = get_last_update()
    return render_template('index.html', api_key=GOOGLE_MAPS_API_KEY, last_update=last_update)

@app.route('/bachelorette')
def bachelorette_page():
    """Bachelorette Party Directory page."""
    return render_template('bachelorette.html', bachelorette_data=bachelorette_data, data=home_data)

@app.route('/about')
def about_page():
    """About Me page."""
    return render_template('about.html', data=home_data)

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
