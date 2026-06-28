import json
from telegram_bot.handlers.base import BaseApprovalHandler
from database.models import db, HappyHourPlace

class HappyHourHandler(BaseApprovalHandler):
    """
    Approval handler for Happy Hour places.
    Saves the extracted Happy Hour data to the database.
    """
    
    def check_duplicate(self, app, data: dict):
        """Check if a place with the same name already exists."""
        name = data.get('name', '').strip()
        if not name:
            return None
            
        with app.app_context():
            # Case insensitive exact match ignoring trailing/leading spaces in DB
            place = HappyHourPlace.query.filter(
                db.func.trim(db.func.lower(HappyHourPlace.name)) == name.lower()
            ).first()
            if place:
                return place.to_dict()
            return None

    def update(self, app, place_id: int, data: dict) -> bool:
        """Update an existing place with new extracted details."""
        try:
            with app.app_context():
                place = HappyHourPlace.query.get(place_id)
                if not place:
                    print(f"❌ Error updating: Place ID {place_id} not found.")
                    return False

                if data.get('name'): place.name = data.get('name')
                if data.get('name_hebrew'): place.name_hebrew = data.get('name_hebrew')
                if data.get('address'): place.address = data.get('address')
                if data.get('city'): place.city = data.get('city')
                if data.get('google_maps_link'): place.google_maps_link = data.get('google_maps_link')
                if data.get('opening_hours'): place.opening_hours = data.get('opening_hours')
                if data.get('description'): place.description = data.get('description')
                if data.get('recommended'): place.recommended = data.get('recommended')
                if data.get('instagram_link'): place.instagram_url = data.get('instagram_link')
                if data.get('reservation_link'): place.reservation_link = data.get('reservation_link')
                if 'kosher' in data: place.kosher = bool(data.get('kosher'))

                db.session.commit()
                print(f"🔄 [SUCCESS] Updated Happy Hour place: {place.name}")
                return True
        except Exception as e:
            import traceback
            print(f"❌ Error updating Happy Hour place:")
            traceback.print_exc()
            return False

    def save(self, app, data: dict) -> bool:
        try:
            with app.app_context():
                place = HappyHourPlace(
                    name=data.get('name', '') or 'Unknown',
                    name_hebrew=data.get('name_hebrew', ''),
                    address=data.get('address', ''),
                    city=data.get('city', ''),
                    google_maps_link=data.get('google_maps_link', ''),
                    opening_hours=data.get('opening_hours', ''),
                    description=data.get('description', ''),
                    recommended=data.get('recommended', ''),
                    instagram_url=data.get('instagram_link', ''),
                    reservation_link=data.get('reservation_link', ''),
                    kosher=bool(data.get('kosher', False)),
                    sunday=False,
                    monday=False,
                    tuesday=False,
                    wednesday=False,
                    thursday=False,
                    friday=False,
                    saturday=False,
                )
                db.session.add(place)
                db.session.commit()
                print(f"🍷 [SUCCESS] Saved Happy Hour place: {place.name}")
                return True
        except Exception as e:
            import traceback
            print(f"❌ Error saving Happy Hour place:")
            traceback.print_exc()
            return False
