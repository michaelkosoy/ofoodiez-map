import os
from dotenv import load_dotenv

# Load environment variables (for standalone running or local tests)
load_dotenv()

# Telegram configurations
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_USER_ID = os.environ.get("TELEGRAM_USER_ID")

# Gemini configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Validate required configuration
def validate_config():
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_USER_ID:
        missing.append("TELEGRAM_USER_ID")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    
    if missing:
        print(f"⚠️ Warning: Missing environment configuration for: {', '.join(missing)}")
        return False
    return True
