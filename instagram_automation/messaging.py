"""
Instagram Messaging API sender.
Handles all outgoing messages: text, private replies, templates, images.
"""
import requests
from .config import Config


class InstagramMessenger:
    """Send messages via the Instagram Graph API."""

    BASE_URL = f"{Config.IG_GRAPH_URL}/{Config.GRAPH_API_VERSION}"

    def _post(self, ig_id, payload, access_token):
        """Internal helper to POST to the messages endpoint."""
        url = f"{self.BASE_URL}/{ig_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            data = resp.json()
            if resp.status_code == 200 and 'message_id' in data:
                print(f"✅ Message sent to {payload.get('recipient', {})}: {data.get('message_id')}")
            else:
                print(f"❌ Message failed: {resp.status_code} - {data}")
            return data
        except Exception as e:
            print(f"❌ Message exception: {e}")
            return {"error": str(e)}

    def send_text(self, ig_id, recipient_id, text, access_token):
        """Send a plain text DM."""
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": text}
        }
        return self._post(ig_id, payload, access_token)

    def send_private_reply(self, ig_id, comment_id, text, access_token):
        """
        Send a private reply (DM) to someone who commented.
        This is the core comment-to-DM feature.
        Constraints: only 1 private reply per comment, within 7 days.
        """
        payload = {
            "recipient": {"comment_id": comment_id},
            "message": {"text": text}
        }
        return self._post(ig_id, payload, access_token)

    def send_button_template(self, ig_id, recipient_id, text, buttons, access_token):
        """
        Send a message with clickable buttons (up to 3).
        buttons: [{"type": "web_url", "url": "...", "title": "..."}]
        """
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "button",
                        "text": text,
                        "buttons": buttons
                    }
                }
            }
        }
        return self._post(ig_id, payload, access_token)

    def send_quick_replies(self, ig_id, recipient_id, text, replies, access_token):
        """
        Send a message with quick reply chips (up to 13).
        replies: [{"content_type": "text", "title": "...", "payload": "..."}]
        """
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "text": text,
                "quick_replies": replies
            }
        }
        return self._post(ig_id, payload, access_token)

    def send_image(self, ig_id, recipient_id, image_url, access_token):
        """Send an image message."""
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {"url": image_url}
                }
            }
        }
        return self._post(ig_id, payload, access_token)

    def send_generic_template(self, ig_id, recipient_id, elements, access_token):
        """
        Send a carousel of cards.
        elements: [{"title": "...", "subtitle": "...", "image_url": "...", "buttons": [...]}]
        """
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "generic",
                        "elements": elements
                    }
                }
            }
        }
        return self._post(ig_id, payload, access_token)

    def get_user_media(self, ig_id, access_token):
        """
        Fetch recent media (posts/reels/videos) for the user.
        Includes local test mockup support.
        """
        if access_token in ('fake_token', 'test_token_123', 'test_token'):
            # Return high-quality food themed mock posts/reels for Tel Aviv food blog ofoodiez
            return [
                {
                    "id": "mock_media_1",
                    "caption": "Check out our new crispy falafel recipe in Tel Aviv! 🧆✨ #ofoodiez #israelifood",
                    "media_type": "VIDEO",
                    "media_url": "https://images.unsplash.com/photo-1547058886-af77d90d7f2e?w=500",
                    "thumbnail_url": "https://images.unsplash.com/photo-1547058886-af77d90d7f2e?w=500",
                    "permalink": "https://instagram.com/p/mock_reel_1",
                    "timestamp": "2026-05-20T12:00:00+0000"
                },
                {
                    "id": "mock_media_2",
                    "caption": "The creamiest hummus bowl you'll ever see 🍲 Creamy, warm, and topped with olive oil. #ofoodiez",
                    "media_type": "IMAGE",
                    "media_url": "https://images.unsplash.com/photo-1574894709920-11b28e7367e3?w=500",
                    "permalink": "https://instagram.com/p/mock_image_2",
                    "timestamp": "2026-05-19T14:30:00+0000"
                },
                {
                    "id": "mock_media_3",
                    "caption": "Sweet and cheesy Knafeh recipe step-by-step! 🧀🍯 Authentic Middle Eastern dessert. Comment KNAFEH for full recipe!",
                    "media_type": "VIDEO",
                    "media_url": "https://images.unsplash.com/photo-1587314168485-3236d6710814?w=500",
                    "thumbnail_url": "https://images.unsplash.com/photo-1587314168485-3236d6710814?w=500",
                    "permalink": "https://instagram.com/p/mock_reel_3",
                    "timestamp": "2026-05-18T09:15:00+0000"
                }
            ]

        # Call Instagram Graph API
        url = f"{self.BASE_URL}/{ig_id}/media"
        params = {
            "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp",
            "access_token": access_token
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if resp.status_code == 200:
                return data.get('data', [])
            else:
                print(f"❌ Get media failed: {resp.status_code} - {data}")
                return []
        except Exception as e:
            print(f"❌ Get media exception: {e}")
            return []


# Singleton instance
messenger = InstagramMessenger()
