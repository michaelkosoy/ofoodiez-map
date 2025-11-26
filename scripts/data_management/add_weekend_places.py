import pandas as pd
import re

raw_text = """
WEEKENDS

שישי

LP עד 20:00 קוקטיילים ב35₪, 20% על האוכל

בר 223 עד 20:00 20% על האלכוהול

רופטופ 98 30% על הכל עד השעה 20:00

פנטסטיק עד 20:00 30% על הכל

תל אה וין בצהריים 1+1 על האלכוהול

נואמה עד 19:00 20% על הכל

לואי עד 19:00 1+1 על האוכל, 20% על האלכוהול

שבת

בר 223 עד 20:00 20% על הכל

LP עד 20:00 קוקטיילים ב35₪, 20% על האוכל 

רופטופ 98 30% על הכל

ליברה עד 20:00 30% על הכל

קונסיירז עד 20:00 25% על האוכל, דרינקים מוזלים

שאטו שועל עד 19:30 50% על האלכוהול,1+1 אוכל

שה ויוי עד 19:30 30% על האלכוהול,20% האוכל

אליבי עד 19:30 20% על הכל

פנטסטיק עד 20:00 30% על הכל

קיצוקאי עד 19:30 1+1 על האלכוהול

אל וסינו עד 19:15 1+1 על כוסות ומנות נבחרות

לני עד 19:00 1+1 על האוכל, 20% על השתייה

מאדאם עד 19:00 30% על הכל

נואמה עד 19:00 20% על הכל

מי וה עד 19:30 25% על האלכוהול

לואי עד 19:00 1+1 על האוכל, 20% על האלכוהול

תל אה וין בצהריים 1+1 על האלכוהול
"""

def parse_weekend_places(text):
    lines = text.strip().split('\n')
    places = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Skip headers
        if line in ["WEEKENDS", "שישי", "שבת"]:
            continue

        # Parse Name and Description
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
            # Fallback
            parts = line.split(' ', 2)
            if len(parts) > 1:
                name = " ".join(parts[:2])
                desc = parts[2] if len(parts) > 2 else ""
            else:
                name = line
                desc = ""
        
        places.append({
            "Name": name,
            "Address": "", 
            "Latitude": "",
            "Longitude": "",
            "Category": "WEEKENDS",
            "Description": desc,
            "ImageURL": ""
        })
        
    return places

new_places = parse_weekend_places(raw_text)

# Load existing data
try:
    df = pd.read_excel('places.xlsx')
    df = df.fillna("")
    
    updated_count = 0
    added_count = 0
    
    # Create a map of existing names for quick lookup
    existing_indices = {name.strip(): i for i, name in enumerate(df['Name'])}
    
    for p in new_places:
        name = p['Name'].strip()
        if name in existing_indices:
            # Update existing
            idx = existing_indices[name]
            df.at[idx, 'Category'] = "WEEKENDS"
            # Update description if it was empty or just to be sure? 
            # User provided specific descriptions for weekends, so let's update it
            df.at[idx, 'Description'] = p['Description']
            updated_count += 1
        else:
            # Add new
            df = pd.concat([df, pd.DataFrame([p])], ignore_index=True)
            added_count += 1
            
    df.to_excel('places.xlsx', index=False)
    print(f"Updated {updated_count} places, Added {added_count} new places.")

except FileNotFoundError:
    pd.DataFrame(new_places).to_excel('places.xlsx', index=False)
    print(f"Created places.xlsx with {len(new_places)} places")
