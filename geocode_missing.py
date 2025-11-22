import pandas as pd
from geopy.geocoders import GoogleV3
from geopy.exc import GeocoderTimedOut
import time

# API Key provided by user
GOOGLE_MAPS_API_KEY = "AIzaSyBdh_bKAGD6ZFbNpq3G_2tmV1BlaedFcPU"
DATA_FILE = 'places.xlsx'
geolocator = GoogleV3(api_key=GOOGLE_MAPS_API_KEY, user_agent="ofoodiez_map")

def geocode_missing():
    try:
        df = pd.read_excel(DATA_FILE)
        df = df.fillna("")
        
        updated_count = 0
        
        for index, row in df.iterrows():
            lat_missing = row['Latitude'] == "" or row['Latitude'] == 0
            lon_missing = row['Longitude'] == "" or row['Longitude'] == 0
            
            if lat_missing or lon_missing:
                location = None
                name = row['Name']
                address = row['Address']
                
                print(f"Geocoding: {name}...")
                
                # Strategy 1: Combined Name + Address (Best for "Not TLV" where Address is City)
                if name and address:
                    try:
                        query = f"{name}, {address}, Israel"
                        location = geolocator.geocode(query, timeout=10)
                        if location:
                            print(f"  Found by Combined: {query}")
                    except Exception as e:
                        print(f"  Error combined: {e}")
                
                # Strategy 2: Name Only + Tel Aviv (Default context if Address missing)
                if not location and name and not address:
                    try:
                        query = f"{name}, Tel Aviv, Israel"
                        location = geolocator.geocode(query, timeout=10)
                        if location:
                            print(f"  Found by Name (TLV default): {query}")
                    except Exception as e:
                        print(f"  Error name: {e}")

                # Strategy 3: Address Only (if Name failed)
                if not location and address:
                    try:
                        query = f"{address}, Israel"
                        location = geolocator.geocode(query, timeout=10)
                        if location:
                            print(f"  Found by Address: {query}")
                    except Exception as e:
                        print(f"  Error address: {e}")

                if location:
                    df.at[index, 'Latitude'] = location.latitude
                    df.at[index, 'Longitude'] = location.longitude
                    updated_count += 1
                else:
                    print(f"  Failed to geocode: {name}")
                
                # Respect API limits
                time.sleep(0.2)
        
        if updated_count > 0:
            df.to_excel(DATA_FILE, index=False)
            print(f"Successfully geocoded {updated_count} places.")
        else:
            print("No places needed geocoding or all failed.")
            
    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    geocode_missing()
