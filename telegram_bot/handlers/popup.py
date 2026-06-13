from telegram_bot.handlers.base import BaseApprovalHandler
from database.models import db, PopupEvent

class PopupHandler(BaseApprovalHandler):
    """
    Approval handler for Pop-up events.
    Saves the event details to the Supabase database.
    """
    
    def save(self, app, data: dict) -> bool:
        with app.app_context():
            try:
                event = PopupEvent(
                    title=data.get('title'),
                    date=data.get('date'),
                    time=data.get('time', ''),
                    location=data.get('location', ''),
                    location_link=data.get('location_link', ''),
                    description=data.get('description', ''),
                    instagram_username=data.get('instagram_username', ''),
                    instagram_link=data.get('instagram_link', ''),
                    image=data.get('image', '')
                )
                db.session.add(event)
                db.session.commit()
                print(f"🎉 Saved popup event to database: {event.title}")
                return True
            except Exception as e:
                db.session.rollback()
                print(f"❌ Error saving popup event to database: {e}")
                return False
