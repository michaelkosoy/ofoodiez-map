import json
from telegram_bot.handlers.base import BaseApprovalHandler
from database.models import db, HappyHourPlace

class HappyHourHandler(BaseApprovalHandler):
    """
    Approval handler for Happy Hour places.
    Saves the extracted Happy Hour data to the SQLite database.
    """
    
    def save(self, app, data: dict) -> bool:
        try:
            with app.app_context():
                # Attempt to parse days if included in description/hours (stubbed as False by default)
                place = HappyHourPlace(
                    name=data.get('name', ''),
                    address=data.get('address', ''),
                    opening_hours=data.get('opening_hours', ''),
                    description=data.get('description', ''),
                    recommended=data.get('recommended', ''),
                    instagram_url=data.get('instagram_link', ''),
                    image_url=data.get('image', ''),
                    # Default all days to True for now, can be edited later
                    sunday=True,
                    monday=True,
                    tuesday=True,
                    wednesday=True,
                    thursday=True,
                    friday=False,
                    saturday=False
                )
                db.session.add(place)
                db.session.commit()
                print(f"🍷 [SUCCESS] Saved Happy Hour place: {place.name}")
                return True
        except Exception as e:
            print(f"❌ Error saving Happy Hour place: {e}")
            return False
