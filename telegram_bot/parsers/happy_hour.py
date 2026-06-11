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
        Analyze this input (which is usually a screenshot of an Instagram Story or Post detailing a Happy Hour deal at a bar/restaurant in Tel Aviv).

        Follow these steps:
        1. Identify the Instagram username of the venue or poster (usually visible at the top-left of the story or profile header).
        2. Using the Instagram username, infer the actual restaurant/bar name. Use your internal knowledge base to find its full physical address in Tel Aviv, regular opening hours, and a standard Google Maps search link.
        3. Read the text/deals written in the image to extract:
           - The exact Happy Hour times and days (e.g., 'Sunday - Thursday 18:00 - 20:00').
           - The specific deals offered (e.g., '1+1 on draft beers', '50% off cocktails & food'). This goes into the 'recommended' field.
        4. Build a short, attractive 1-2 sentence description in English summarizing the deals and the restaurant/bar's vibe.
        5. Provide the official Instagram handle link (e.g., 'https://instagram.com/handle').

        You must return a single JSON object matching this schema:
        {
          "name": "Restaurant/Bar Name",
          "address": "Full physical address, Tel Aviv",
          "google_maps_link": "Google Maps search link",
          "opening_hours": "Regular hours & Happy Hour times/days",
          "recommended": "Specific deals (e.g., 50% off all drinks)",
          "description": "Short description of the vibe and deals",
          "instagram_username": "@handle",
          "instagram_link": "Instagram URL"
        }
        Do not add any markdown formatting outside the JSON block. Return ONLY the raw JSON string.
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
