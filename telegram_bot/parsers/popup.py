import json
from datetime import datetime
import google.generativeai as genai
from telegram_bot.parsers.base import BaseEventParser
from telegram_bot.config import GEMINI_API_KEY

class PopupParser(BaseEventParser):
    """
    Parser for Pop-up events.
    Uses Gemini 1.5 Flash to structure data from flyer photos or text.
    """
    
    def __init__(self):
        if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
        else:
            self.model = None

    def get_prompt(self, current_date_str: str) -> str:
        return f"""
        Analyze this input (which is usually a flyer or text detailing a pop-up food event). Today's date is {current_date_str}.

        Follow these steps:
        1. Identify the name of the pop-up or chef.
        2. Identify the date of the event (convert to YYYY-MM-DD format). If the date is displayed without a year (like "14.06" or "June 14"), use the current year from today's date ({current_date_str}).
        3. Identify the time of the event.
        4. Identify the location/venue name and full address.
        5. Build a short, attractive 1-2 sentence description in English summarizing the menu, chef, and vibe of the pop-up.
        6. Extract or look up the host's or venue's Instagram handle and provide its Instagram URL.

        CRITICAL: If any information is missing or cannot be found in the image/text, DO NOT fail. Instead, leave the corresponding field as an empty string ("") so the user can fill it in manually later.

        You must return a single JSON object matching this schema:
        {{
          "title": "...",
          "date": "YYYY-MM-DD",
          "time": "Pop-up time, e.g. 18:00 - 23:00",
          "location": "Venue name & Full Address",
          "location_link": "Google Maps Link",
          "description": "...",
          "instagram_username": "@...",
          "instagram_link": "..."
        }}
        Do not add any markdown formatting outside the JSON block. Return ONLY the raw JSON string.
        """


    def parse_text(self, text: str) -> dict:
        if not self.model:
            raise ValueError("GEMINI_API_KEY is not configured in .env file.")
        
        current_date_str = datetime.now().strftime("%Y-%m-%d")
        response = self.model.generate_content(
            [self.get_prompt(current_date_str), f"Input text to analyze:\n{text}"],
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text.strip())

    def parse_image(self, image_bytes: bytes, mime_type: str) -> dict:
        if not self.model:
            raise ValueError("GEMINI_API_KEY is not configured in .env file.")
        
        current_date_str = datetime.now().strftime("%Y-%m-%d")
        image_part = {
            'mime_type': mime_type,
            'data': image_bytes
        }
        response = self.model.generate_content(
            [self.get_prompt(current_date_str), image_part],
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text.strip())
