import pandas as pd
import re

raw_text = """
not tlv

גבעתיים

זוט אלורס- 20% על הכל עד 20:00

ויני בר יין- 25% על הכל עד 19:30

ג’ונו- 20% על הכל עד 19:00

יין- 30% על הכוסות יין עד 20:00

בוטה- 25% על התפריט עד השעה 19:00

מרלן 15% על האוכל בין 18-20

קפה נלסון 1+1 על הדרינקים בין 16:30-19:30

רמת גן

שולה בחצר - 25% על הכל עד 19

פרוג ושות׳- 20% על אוכל ושתייה נבחרים בין 18:30-20:30

הספסל- בירה ב23₪ עד השעה 19, ערבי ספיישל כל יום

סווינג בר- 1+1 על האלכוהול בין 17-20

פלאזה רמת גן- 1+1 על הפיצה או 10% על התפריט בין 19-20 ולייט נייט בין 23-24 עם 20% על הכל

מרסלה בר יין- 25% על הדרינקים עד 19, כוס יין ב19₪

רופטופ 360- 50% על הקוקטיילים בין 19-20:30

פתח תקווה

בייקר סלון- 25% על הכל בין 19:00-20:00

קולולו- 30% על האלכוהול עד 19:30

יקב לוינסון 20% על הכל בין 16-19 בשני עד חמישי

קריית אונו

ג’ונז פיצה בר- 50% על הקוקטיילים עד 20:00, ימי שישי החל מ21:00 ו30% על הראשונות

סימפוני- 20% הנחה על הכל

רובע בר יין- מ17-19, 50% על האלכוהול, 20% על האוכל

סביון 

מילה 1+1 על הדרינקים בין 17-19

מזרחית לת״א

not tlv


ראשון לציון

ויני קולטורה- 20% על האוכל,1+1 על כוסות, עד 20:00 גם בסופש

עלינא-40% על האלכוהול עד 20:30, ימי שני יין ללא תחתית

סה טו בר פיצות- 1+1 על הקוקטיילים כל שלישי כל הערב


באר שבע

חייאתי טאפס בר ים תיכוני- 19-20:30 50% על האלכוהול ו20% על המנה השניה באמצע שבוע

בסטורי- עד 19:00

שאטו ד’אור- 20% כל הכל שני עד חמישי ושבת מ19:00-20:30

הרצליה

ג’וני בר יין- 1+1 על הכוסות עד 19:30

מוניציפאל- 50% על האלכוהול,20% על האוכל עד 20:00

ערב- 25% על הכל עד 20:30

קיוטו- בין 16:30-1830

רעננה

הא ודא בר יין- 1+1 על הכוסות,20% על האוכל בין 16:00-19:30

אוגסטין- 1+1 על האלכוהול עד 19:00


רמת השרון

ג’ולין בר יין-1+1 על הכוסות עד 19:30


הוד השרון

פלאזה קפה 25% על הכל עד 19:00

פורטונה 25% על הכל עד 19:00


כפר סבא

ספארי סאן-50% על האלכוהול ו20% על האוכל עד 20:00  

אריאנה- 20% על הכל עד 19:30


נתניה

הייד- 1+1 עד 19:00 על הבירות והקוקטיילים

איזור השרון
"""

def parse_not_tlv(text):
    lines = text.strip().split('\n')
    places = []
    current_city = ""
    
    # List of known cities/headers to detect
    cities = [
        "גבעתיים", "רמת גן", "פתח תקווה", "קריית אונו", "סביון", 
        "ראשון לציון", "באר שבע", "הרצליה", "רעננה", "רמת השרון", 
        "הוד השרון", "כפר סבא", "נתניה", "איזור השרון", "מזרחית לת״א"
    ]
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if line is a city header
        if line in cities or line.replace(':', '') in cities:
            current_city = line.replace(':', '').strip()
            continue
            
        if "not tlv" in line.lower():
            continue

        # Parse Name and Description
        # Heuristic: Look for hyphen or number
        if '-' in line:
            parts = line.split('-', 1)
            name = parts[0].strip()
            desc = parts[1].strip()
        else:
            # Fallback logic
            match = re.search(r'\d', line)
            if match:
                idx = match.start()
                split_idx = line.rfind(' ', 0, idx)
                if split_idx != -1:
                    name = line[:split_idx].strip()
                    desc = line[split_idx:].strip()
                else:
                    name = line[:idx].strip()
                    desc = line[idx:].strip()
            else:
                name = line
                desc = ""
        
        # Use city as initial address to help geocoding
        address_hint = current_city if current_city else ""
        
        places.append({
            "Name": name,
            "Address": address_hint, # Will be used by geocoder
            "Latitude": "",
            "Longitude": "",
            "Category": "Not TLV",
            "Description": desc,
            "ImageURL": ""
        })
        
    return places

new_places = parse_not_tlv(raw_text)
df_new = pd.DataFrame(new_places)

# Load existing data
try:
    df_existing = pd.read_excel('places.xlsx')
    # Filter out empty names from existing
    df_existing = df_existing[df_existing['Name'].str.strip().astype(bool)]
    
    # Append new data (avoiding duplicates if possible, but simple append for now)
    # We can check if name exists
    existing_names = set(df_existing['Name'].astype(str).str.strip())
    
    filtered_new_places = []
    for p in new_places:
        if p['Name'].strip() not in existing_names:
            filtered_new_places.append(p)
            
    if filtered_new_places:
        df_new_filtered = pd.DataFrame(filtered_new_places)
        df_combined = pd.concat([df_existing, df_new_filtered], ignore_index=True)
        df_combined.to_excel('places.xlsx', index=False)
        print(f"Added {len(filtered_new_places)} new places to places.xlsx")
    else:
        print("No new places to add (all duplicates).")

except FileNotFoundError:
    df_new.to_excel('places.xlsx', index=False)
    print(f"Created places.xlsx with {len(new_places)} places")
