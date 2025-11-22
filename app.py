from flask import Flask, jsonify, render_template
import pandas as pd
import os
from geopy.geocoders import GoogleV3
from geopy.exc import GeocoderTimedOut
from dotenv import load_dotenv
import requests
from io import StringIO

# Load environment variables from .env file (for local development)
load_dotenv()

app = Flask(__name__, 
            static_url_path='/static',
            static_folder='static',
            template_folder='templates')

# API Key from environment variable
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')

if not GOOGLE_MAPS_API_KEY:
    raise ValueError("GOOGLE_MAPS_API_KEY environment variable is not set")

# Google Sheets URL (converted to CSV export)
SHEET_ID = '1yvXOS3l_0Wr0SxLf9YZE8RaFzwgQop4MshD5pbtmwzA'
SHEET_URL = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv'

# Fallback to local file if Google Sheets is unavailable
DATA_FILE = 'places.xlsx'

geolocator = GoogleV3(api_key=GOOGLE_MAPS_API_KEY, user_agent="ofoodiez_map")

@app.route('/')
def index():
    return render_template('index.html', api_key=GOOGLE_MAPS_API_KEY)

@app.route('/api/places')
def get_places():
    try:
        # Try to fetch from Google Sheets first
        try:
            response = requests.get(SHEET_URL, timeout=10)
            response.raise_for_status()
            # Specify UTF-8 encoding to preserve Hebrew characters
            df = pd.read_csv(StringIO(response.content.decode('utf-8')))
            print("✓ Loaded data from Google Sheets")
        except Exception as e:
            print(f"⚠️  Could not load from Google Sheets: {e}")
            # Fallback to local Excel file
            if not os.path.exists(DATA_FILE):
                return jsonify({"error": "Data source not available"}), 404
            df = pd.read_excel(DATA_FILE)
            print("✓ Loaded data from local Excel file")
        
        # Fill NaN values with empty string to avoid JSON errors
        df = df.fillna("")
        # Filter out rows where Name is empty
        df = df[df['Name'].str.strip().astype(bool)]
        
        places = df.to_dict(orient='records')
        return jsonify(places)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
