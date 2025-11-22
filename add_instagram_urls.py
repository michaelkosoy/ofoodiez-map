import pandas as pd

DATA_FILE = 'places.xlsx'

# Dictionary mapping Hebrew names to Instagram URLs
instagram_urls = {
    "קפה אירופה": "https://www.instagram.com/cafe_europa_tlv/",
    "ורמוטריה": "https://www.instagram.com/vermuteria.tlv/",
    "ציקטי": "https://www.instagram.com/cicchettitlv/",
    "ג'ורג וגון": "https://www.instagram.com/georgeandjohn_tlv/",
    "OCD": "https://www.instagram.com/ocd_tlv/",
    "לני": "https://www.instagram.com/leny.tlv/",
    "רומנו": "https://www.instagram.com/romano_tlv/",
    "מיזנון": "https://www.instagram.com/miznon_il/",
    "הכוסם": "https://www.instagram.com/hakosemofficial/",
    "בר 51": "https://www.instagram.com/bar51tlv/",
    "פורט סעיד": "https://www.instagram.com/port_said/",
    "שילה": "https://www.instagram.com/shila_rest/",
    "טאיזו": "https://www.instagram.com/taizu_tlv/",
    "משיה": "https://www.instagram.com/mashya_tlv/",
    "סנטה קתרינה": "https://www.instagram.com/santakatarina2/",
    "אוזריה": "https://www.instagram.com/ouzeria_tlv/",
    "דלידה": "https://www.instagram.com/dalidatlv/",
    "ג'וז ולוז": "https://www.instagram.com/jozveloz/",
    "טדר": "https://www.instagram.com/teder.fm/",
    "דוק": "https://www.instagram.com/dok_tlv/",
    "ווייס": "https://www.instagram.com/weiss_tlv/",
    "הבנות": "https://www.instagram.com/habanot_tlv/",
    "מרלן": "https://www.instagram.com/marlen_tlv/",
}

def update_instagram_urls():
    try:
        df = pd.read_excel(DATA_FILE)
        df = df.fillna("")
        
        updated_count = 0
        
        for name, url in instagram_urls.items():
            # Try exact match first
            mask = df['Name'].str.strip() == name
            if mask.any():
                # Only update if currently empty
                empty_mask = mask & (df['InstagramURL'] == "")
                if empty_mask.any():
                    df.loc[empty_mask, 'InstagramURL'] = url
                    updated_count += empty_mask.sum()
                    print(f"✓ Updated {name}")
            else:
                # Try partial match
                mask = df['Name'].str.contains(name, case=False, na=False, regex=False)
                if mask.any():
                    empty_mask = mask & (df['InstagramURL'] == "")
                    if empty_mask.any():
                        df.loc[empty_mask, 'InstagramURL'] = url
                        updated_count += empty_mask.sum()
                        print(f"✓ Updated {name} (partial match)")
                else:
                    print(f"✗ Not found: {name}")
        
        if updated_count > 0:
            df.to_excel(DATA_FILE, index=False)
            print(f"\n✅ Successfully updated {updated_count} Instagram URLs!")
        else:
            print("\n⚠️  No new URLs added (all already populated or names not found)")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    update_instagram_urls()
