import pandas as pd
from geopy.geocoders import GoogleV3
import time

# API Key provided by user
GOOGLE_MAPS_API_KEY = "AIzaSyBdh_bKAGD6ZFbNpq3G_2tmV1BlaedFcPU"
geolocator = GoogleV3(api_key=GOOGLE_MAPS_API_KEY, user_agent="ofoodiez_map_address_finder")

DATA_FILE = 'places.xlsx'

try:
    df = pd.read_excel(DATA_FILE)
    df = df.fillna("")
    
    updated_count = 0
    
    print(f"Scanning {len(df)} places for missing addresses...")
    
    for index, row in df.iterrows():
        # Check if Address is missing but Name exists
        address_missing = not row.get('Address')
        name = row.get('Name')
        
        if address_missing and name:
            try:
                # Search for the place in Tel Aviv area
                # We append "Tel Aviv, Israel" to help context, but Google is smart
                query = f"{name}, Tel Aviv, Israel"
                location = geolocator.geocode(query, timeout=10)
                
                if location:
                    # Update Address
                    df.at[index, 'Address'] = location.address
                    # Also update Lat/Lon while we're at it
                    df.at[index, 'Latitude'] = location.latitude
                    df.at[index, 'Longitude'] = location.longitude
                    
                    print(f"Found: {name} -> {location.address}")
                    updated_count += 1
                else:
                    print(f"Not found: {name}")
                    
            except Exception as e:
                print(f"Error searching for {name}: {e}")
            
            # Be nice to the API
            time.sleep(0.1)
            
    if updated_count > 0:
        df.to_excel(DATA_FILE, index=False)
        print(f"\nSuccessfully updated {updated_count} places with addresses!")
    else:
        print("\nNo new addresses found.")

except Exception as e:
    print(f"Error: {e}")
