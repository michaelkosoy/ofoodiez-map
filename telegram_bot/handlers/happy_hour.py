from telegram_bot.handlers.base import BaseApprovalHandler

class HappyHourHandler(BaseApprovalHandler):
    """
    Skeleton approval handler for Happy Hour places.
    To be fully implemented in a future phase.
    """
    
    def save(self, app, data: dict) -> bool:
        # Simple placeholder implementation
        print(f"🍷 [MOCK] Saving Happy Hour place: {data.get('name')}")
        return True
