import pandas as pd

DATA_FILE = 'places.xlsx'

try:
    df = pd.read_excel(DATA_FILE)
    
    # Replace "Restaurant" with empty string in Category column
    if 'Category' in df.columns:
        count = 0
        for index, row in df.iterrows():
            if row['Category'] == 'Restaurant':
                df.at[index, 'Category'] = ''
                count += 1
        
        if count > 0:
            df.to_excel(DATA_FILE, index=False)
            print(f"Removed 'Restaurant' category from {count} places.")
        else:
            print("No 'Restaurant' categories found to remove.")
            
except Exception as e:
    print(f"Error: {e}")
