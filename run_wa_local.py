"""Local-only dev server for the WhatsApp bot.

Mounts ONLY the whatsapp_bot blueprint on a throwaway local SQLite DB and runs
db.create_all() AFTER the models are imported, so — unlike app.py — it *does*
create the wa_ tables locally. Deliberately skips the Telegram bot, Google Maps,
Gemini, and Instagram routes, so you can test the WhatsApp webhook in isolation
without those deps/secrets and with zero risk of stealing production Telegram
polling.

Usage (from the repo root, with ngrok pointing at the same port):

    TWILIO_WEBHOOK_URL='https://<your-ngrok-id>.ngrok-free.app/wa/webhook' \
        ./venv/bin/python run_wa_local.py

TWILIO_AUTH_TOKEN is read from your .env automatically (shell env still wins).
TWILIO_WEBHOOK_URL MUST equal the exact public URL Twilio posts to (your ngrok
URL) or signature validation rejects every request with 403.
"""
import os

from dotenv import load_dotenv
from flask import Flask

from database.models import db
from whatsapp_bot import init_app as init_wa_bot

load_dotenv()  # picks up TWILIO_AUTH_TOKEN from .env; shell env still wins

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///wa_local.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

init_wa_bot(app)  # registers wa_bp + imports the wa_ models
db.init_app(app)
with app.app_context():
    db.create_all()  # creates wa_ (and ig_) tables in wa_local.db

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))  # 5001, not 5000 (macOS AirPlay)
    print(f"WhatsApp bot dev server -> http://127.0.0.1:{port}/wa/webhook")
    print(f"Signature pinned to TWILIO_WEBHOOK_URL="
          f"{os.environ.get('TWILIO_WEBHOOK_URL', '(default onrender URL)')}")
    app.run(port=port, debug=True, use_reloader=False)
