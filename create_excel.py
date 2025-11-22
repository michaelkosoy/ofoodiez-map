import pandas as pd

data = {
    "Name": ["Port Sa'id", "Romano", "Miznon", "HaKosem", "Vitrina"],
    "Address": ["Har Sinai St 5, Tel Aviv-Yafo", "Derech Jaffa 9, Tel Aviv-Yafo", "King George St 30, Tel Aviv-Yafo", "Shlomo Ibn Gabirol St 19, Tel Aviv-Yafo", "Lilienblum St 40, Tel Aviv-Yafo"],
    "Latitude": [32.0626, 32.0618, 32.0715, 32.0754, 32.0710],
    "Longitude": [34.7715, 34.7712, 34.7793, 34.7757, 34.7790],
    "Category": ["Restaurant", "Bar", "Street Food", "Street Food", "Burger"],
    "Description": ["Hip restaurant by Eyal Shani", "Lively bar with great food", "Famous pita place", "Best falafel in town", "Amazing burgers"],
    "ImageURL": ["", "", "", "", ""]
}

df = pd.DataFrame(data)
df.to_excel("places.xlsx", index=False)
print("places.xlsx created successfully")
