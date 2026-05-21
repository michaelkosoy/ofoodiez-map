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


# Singleton instance
messenger = InstagramMessenger()
