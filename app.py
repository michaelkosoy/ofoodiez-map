from flask import Flask, jsonify, render_template
import pandas as pd
import os
from geopy.geocoders import GoogleV3
from geopy.exc import GeocoderTimedOut
from dotenv import load_dotenv

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

DATA_FILE = 'places.xlsx'
geolocator = GoogleV3(api_key=GOOGLE_MAPS_API_KEY, user_agent="ofoodiez_map")

@app.route('/')
def index():
    return render_template('index.html', api_key=GOOGLE_MAPS_API_KEY)

@app.route('/api/places')
def get_places():
    if not os.path.exists(DATA_FILE):
        return jsonify({"error": "Data file not found"}), 404
    
    try:
        df = pd.read_excel(DATA_FILE)
        # Fill NaN values with empty string to avoid JSON errors
        df = df.fillna("")
        # Filter out rows where Name is empty
        df = df[df['Name'].str.strip().astype(bool)]
        
        # Check if we need to geocode
        updated = False
        if 'Address' in df.columns:
            for index, row in df.iterrows():
                # If lat/lon are missing (empty string or 0 or None)
                lat_missing = row.get('Latitude') == "" or row.get('Latitude') == 0 or pd.isna(row.get('Latitude'))
                lon_missing = row.get('Longitude') == "" or row.get('Longitude') == 0 or pd.isna(row.get('Longitude'))
                
                if lat_missing and lon_missing:
                    location = None
                if lat_missing and lon_missing:
                    location = None
                    
                    # Best Strategy: Combine Name and Address
                    # This finds the specific venue (e.g. Romano inside Beit Romano) 
                    # AND ensures the correct branch (e.g. Miznon King George vs Sarona)
                    if row.get('Name') and row.get('Address'):
                        try:
                            query = f"{row['Name']}, {row['Address']}, Israel"
                            location = geolocator.geocode(query, timeout=10)
                            if location:
                                print(f"Geocoded by Combined: {query} -> {location.latitude}, {location.longitude}")
                        except Exception as e:
                            print(f"Error geocoding combined {row['Name']}: {e}")

                    # Fallback: Address Only (if Name + Address failed)
                    if not location and row.get('Address'):
                        try:
                            query = f"{row['Address']}, Israel"
                            location = geolocator.geocode(query, timeout=10)
                            if location:
                                print(f"Geocoded by Address: {query} -> {location.latitude}, {location.longitude}")
                        except Exception as e:
                            print(f"Error geocoding address {row['Address']}: {e}")

                    # Fallback: Name Only (if Address is missing)
                    if not location and row.get('Name') and not row.get('Address'):
                        try:
                            query = f"{row['Name']}, Tel Aviv"
                            location = geolocator.geocode(query, timeout=10)
                            if location:
                                print(f"Geocoded by Name: {query} -> {location.latitude}, {location.longitude}")
                        except Exception as e:
                            print(f"Error geocoding name {row['Name']}: {e}")

                    if location:
                        df.at[index, 'Latitude'] = location.latitude
                        df.at[index, 'Longitude'] = location.longitude
                        updated = True
        
        if updated:
            try:
                df.to_excel(DATA_FILE, index=False)
                print("Updated Excel file with new coordinates")
            except Exception as e:
                print(f"Could not save updated Excel file (might be open): {e}")

        places = df.to_dict(orient='records')
        return jsonify(places)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
