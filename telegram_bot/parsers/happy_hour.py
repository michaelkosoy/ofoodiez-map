import json
import google.generativeai as genai
from telegram_bot.parsers.base import BaseEventParser
from telegram_bot.config import GEMINI_API_KEY

class HappyHourParser(BaseEventParser):
    """
    Parser for Happy Hour places.
    Uses Gemini 1.5 Flash to extract restaurant details and deals from Instagram screenshots.
    """
    
    def __init__(self):
        if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
        else:
            self.model = None

    def get_prompt(self) -> str:
        return """
        Analyze this input (a screenshot of an Instagram Story/Post or text describing a Happy Hour deal at a bar/restaurant, likely in Tel Aviv or Israel).

        Use BOTH the content in the image/text AND your own knowledge base about the venue to fill in as many fields as possible.

        Steps:
        1. Identify the Instagram username of the venue (top-left of story or profile header).
        2. Using the username and any visible text, identify the restaurant/bar name in English and in Hebrew.
           - If the name is only in Hebrew, transliterate/translate it to English for the "name" field.
           - If the name is only in English, translate it to Hebrew for the "name_hebrew" field.
        3. Use your knowledge to find the venue's full physical address and city (e.g. "Tel Aviv", "Herzliya").
        4. Build a Google Maps search link for the venue (format: https://www.google.com/maps/search/?api=1&query=VENUE+NAME+CITY).
        5. Extract the Happy Hour times and days from the flyer (e.g. "Sunday–Thursday 18:00–20:00").
        6. Write a single rich description in English that covers BOTH the venue vibe AND the specific deals offered (e.g. "A lively rooftop bar with 1+1 cocktails and 50% off food, Sunday–Thursday from 18:00.").
        7. If there is a video or Reel URL visible in the content, put it in "recommended". Otherwise leave it empty.
        8. Provide the Instagram handle and full profile URL.
        9. Use your knowledge to determine if the venue is kosher (true/false).
        10. Search your knowledge for a reservation link for this venue — check only Tabit (https://tabit.cloud) or Ontopo (https://ontopo.com). If found on either, provide the direct booking URL. If not found on either, leave empty.

        CRITICAL: Never fail due to missing info — leave unknown fields as empty string "" or false. Return ONLY a raw JSON object with no markdown.

        JSON schema:
        {
          "name": "Restaurant/Bar name in English",
          "name_hebrew": "שם בעברית",
          "address": "Full street address",
          "city": "City name in English",
          "google_maps_link": "https://www.google.com/maps/search/...",
          "opening_hours": "Happy Hour days and times as written on flyer",
          "description": "Vibe + deals combined, 2-3 sentences in English",
          "recommended": "Video/Reel URL if present, otherwise empty string",
          "instagram_username": "@handle",
          "instagram_link": "https://instagram.com/handle",
          "kosher": false,
          "reservation_link": "Tabit or Ontopo booking URL, or empty string"
        }
        """

    def parse_text(self, text: str) -> dict:
        if not self.model:
            raise ValueError("GEMINI_API_KEY is not configured in .env file.")
        
        response = self.model.generate_content(
            [self.get_prompt(), f"Input text to analyze:\n{text}"],
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text.strip())

    def parse_image(self, image_bytes: bytes, mime_type: str) -> dict:
        if not self.model:
            raise ValueError("GEMINI_API_KEY is not configured in .env file.")
        
        image_part = {
            'mime_type': mime_type,
            'data': image_bytes
        }
        response = self.model.generate_content(
            [self.get_prompt(), image_part],
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text.strip())
