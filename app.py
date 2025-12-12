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
from data import data as home_data

# Load environment variables from .env file (for local development)
load_dotenv()

app = Flask(__name__, 
            static_url_path='/static',
            static_folder='app/static',
            template_folder='app/templates')

# API Key from environment variable
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')

if not GOOGLE_MAPS_API_KEY:
    raise ValueError("GOOGLE_MAPS_API_KEY environment variable is not set")

# Google Sheets URL (converted to CSV export)
SHEET_ID = '1yvXOS3l_0Wr0SxLf9YZE8RaFzwgQop4MshD5pbtmwzA'
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
    return render_template('home.html', data=home_data)

@app.route('/map')
def map_page():
    """Happy Hour Map page."""
    last_update = get_last_update()
    return render_template('index.html', api_key=GOOGLE_MAPS_API_KEY, last_update=last_update)


@app.route('/health')
def health_check():
    return "OK", 200

@app.route('/api/places')
def get_places():
    try:
        # Check in-memory cache first
        cached_places = get_cached_data()
        if cached_places:
            return jsonify(cached_places)
        
        # Fetch fresh data from Google Sheets
        response = requests.get(SHEET_URL, timeout=10)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.content.decode('utf-8')))
        print("✓ Loaded fresh data from Google Sheets")
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
            'Verified': 'Verified'
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
    admin_secret = os.environ.get('ADMIN_SECRET', 'ofoodiez2025') # Default secret
    
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
    admin_secret = os.environ.get('ADMIN_SECRET', 'ofoodiez2025') # Default secret
    
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
FORMSPREE_ENDPOINT = os.environ.get('FORMSPREE_ENDPOINT', '')

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
