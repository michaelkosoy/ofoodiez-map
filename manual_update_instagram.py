import pandas as pd

DATA_FILE = 'places.xlsx'

# Dictionary of Name -> Instagram URL
manual_updates = {
    "Port Sa'id": "https://www.instagram.com/port_said/", # Verifying this one
    "Romano": "https://www.instagram.com/romano_tlv/", # Likely
    "Miznon": "https://www.instagram.com/miznon_il/",
    "HaKosem": "https://www.instagram.com/hakosemofficial/",
    "Bar 51": "https://www.instagram.com/bar51tlv/",
    "George & John": "https://www.instagram.com/georgeandjohn_tlv/",
    "OCD": "https://www.instagram.com/ocd_tlv/",
    "Shila": "https://www.instagram.com/shila_rest/",
    "Taizu": "https://www.instagram.com/taizu_tlv/",
    "Mashya": "https://www.instagram.com/mashya_tlv/",
    "Santa Katarina": "https://www.instagram.com/santakatarina2/",
    "Ouzeria": "https://www.instagram.com/ouzeria_tlv/",
    "Dalida": "https://www.instagram.com/dalidatlv/",
    "Joz ve Loz": "https://www.instagram.com/jozveloz/",
    "Teder.fm": "https://www.instagram.com/teder.fm/",
    "Dok": "https://www.instagram.com/dok_tlv/",
    "A": "https://www.instagram.com/a_restaurant_tlv/",
    "Weiss": "https://www.instagram.com/weiss_tlv/",
    "Habanot": "https://www.instagram.com/habanot_tlv/",
    "Cicchetti": "https://www.instagram.com/cicchettitlv/",
}

def update_instagram():
    try:
        df = pd.read_excel(DATA_FILE)
        df = df.fillna("")
        
        updated_count = 0
        
        for name, url in manual_updates.items():
            # Find the row with this name (partial match or exact)
            # Let's try exact first, then contains
            mask = df['Name'].str.strip().str.lower() == name.lower()
            if mask.any():
                df.loc[mask, 'InstagramURL'] = url
                updated_count += 1
                print(f"Updated {name}")
            else:
                # Try contains
                mask = df['Name'].str.contains(name, case=False, na=False)
                if mask.any():
                    df.loc[mask, 'InstagramURL'] = url
                    updated_count += 1
                    print(f"Updated {name} (partial match)")
        
        if updated_count > 0:
            df.to_excel(DATA_FILE, index=False)
            print(f"Successfully manually updated {updated_count} places.")
        else:
            print("No places matched for manual update.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    update_instagram()
