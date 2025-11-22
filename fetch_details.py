import pandas as pd
import requests
import time
import json

# API Key provided by user
GOOGLE_MAPS_API_KEY = "AIzaSyBdh_bKAGD6ZFbNpq3G_2tmV1BlaedFcPU"
DATA_FILE = 'places.xlsx'

def get_place_details(name, address):
    # 1. Search for the place ID
    search_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    query = f"{name} {address}"
    params = {
        "input": query,
        "inputtype": "textquery",
        "fields": "place_id",
        "key": GOOGLE_MAPS_API_KEY
    }
    
    try:
        response = requests.get(search_url, params=params)
        data = response.json()
        
        if data.get("candidates"):
            place_id = data["candidates"][0]["place_id"]
            
            # 2. Get Place Details
            details_url = "https://maps.googleapis.com/maps/api/place/details/json"
            details_params = {
                "place_id": place_id,
                "fields": "opening_hours,website,url", # url is Google Maps link, website is official site
                "key": GOOGLE_MAPS_API_KEY
            }
            
            details_response = requests.get(details_url, params=details_params)
            details_data = details_response.json()
            
            result = {}
            if details_data.get("result"):
                res = details_data["result"]
                
                # Opening Hours
                if "opening_hours" in res and "weekday_text" in res["opening_hours"]:
                    # Join with <br> for HTML display
                    result["OpeningHours"] = "<br>".join(res["opening_hours"]["weekday_text"])
                
                # Website / Instagram
                # Check if website field contains instagram
                if "website" in res:
                    website = res["website"]
                    if "instagram.com" in website.lower():
                        result["InstagramURL"] = website
                    else:
                        # Store website anyway for reference
                        result["Website"] = website
                
                # Also check editorial_summary or other fields that might have social links
                # Google Places API doesn't always return Instagram directly, 
                # but we can try to extract from website
                
            return result
            
    except Exception as e:
        print(f"Error fetching details for {name}: {e}")
        return None
    
    return None

def update_excel_with_details():
    try:
        df = pd.read_excel(DATA_FILE)
        df = df.fillna("")
        
        # Add columns if they don't exist
        if 'OpeningHours' not in df.columns:
            df['OpeningHours'] = ""
        if 'InstagramURL' not in df.columns:
            df['InstagramURL'] = ""
            
        updated_count = 0
        
        for index, row in df.iterrows():
            # Only fetch if missing (or force update if needed, but let's save API calls)
            if not row['OpeningHours'] or not row['InstagramURL']:
                print(f"Fetching details for: {row['Name']}...")
                
                details = get_place_details(row['Name'], row['Address'])
                
                if details:
                    if "OpeningHours" in details and not row['OpeningHours']:
                        df.at[index, 'OpeningHours'] = details["OpeningHours"]
                        print(f"  Found Opening Hours")
                    
                    if "InstagramURL" in details and not row['InstagramURL']:
                        df.at[index, 'InstagramURL'] = details["InstagramURL"]
                        print(f"  Found Instagram URL")
                    elif "Website" in details and not row['InstagramURL']:
                         # If we found a website but it's not instagram, maybe put it somewhere?
                         # For now, user asked for Instagram. 
                         # Let's check if the website is relevant.
                         pass
                    
                    updated_count += 1
                    time.sleep(0.2) # Rate limiting
                else:
                    print("  No details found.")
        
        if updated_count > 0:
            df.to_excel(DATA_FILE, index=False)
            print(f"Successfully updated details for {updated_count} places.")
        else:
            print("No new details found.")
            
    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    update_excel_with_details()
