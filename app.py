from flask import Flask, jsonify, render_template
import pandas as pd
import os
import json
from datetime import datetime, timedelta
from geopy.geocoders import GoogleV3
from geopy.exc import GeocoderTimedOut
from dotenv import load_dotenv
import requests
from io import StringIO

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


# ============ ROUTES ============

@app.route('/')
def index():
    return render_template('index.html', api_key=GOOGLE_MAPS_API_KEY)

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
            'Longitude': 'Longitude'
        }
        
        # Drop duplicate columns (keep the first one)
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Drop the InstagramURL column if it exists (we only use Instagram Link)
        if 'InstagramURL' in df.columns:
            df = df.drop(columns=['InstagramURL'])
        
        # Rename columns that exist in the mapping
        df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})
        
        # Fill NaN values with empty string to avoid JSON errors
        df = df.fillna("")
        
        # Filter out rows where Name is empty (if Name column exists)
        if 'Name' in df.columns:
            df = df[df['Name'].str.strip().astype(bool)]
        
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
    clear_data_cache()
    return jsonify({"status": "Cache cleared. Next request will fetch fresh data."})

if __name__ == '__main__':
    app.run(debug=True)
