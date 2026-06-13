"""Résumé file handling: download from Twilio media, store in Supabase Storage.

Both are config-gated and best-effort: if the Supabase Storage env vars are
unset, upload_resume returns None — the application is still recorded and the
résumé bytes are still available in-request for the advocate email; the file
just isn't durably stored.
"""
import logging
import uuid

import requests

from .config import WaConfig

logger = logging.getLogger("whatsapp_bot")

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def download_twilio_media(media_url):
    """Download media bytes from a Twilio MediaUrl (HTTP basic auth).
    Returns (content_bytes, content_type) or (None, None) on failure/oversize."""
    try:
        resp = requests.get(
            media_url,
            auth=(WaConfig.TWILIO_ACCOUNT_SID, WaConfig.TWILIO_AUTH_TOKEN),
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.content
        if len(content) > _MAX_BYTES:
            logger.warning("wa résumé too large: %d bytes", len(content))
            return None, None
        return content, resp.headers.get("Content-Type", "")
    except Exception:
        logger.exception("wa: failed to download Twilio media")
        return None, None


def upload_resume(user_id, content):
    """Upload résumé bytes to the private Supabase Storage bucket. Returns the
    object path, or None if Storage isn't configured / the upload failed."""
    base = WaConfig.SUPABASE_URL
    key = WaConfig.SUPABASE_SERVICE_ROLE_KEY
    if not base or not key:
        return None
    path = f"applications/{user_id}/{uuid.uuid4().hex}.pdf"
    try:
        resp = requests.post(
            f"{base.rstrip('/')}/storage/v1/object/{WaConfig.SUPABASE_RESUME_BUCKET}/{path}",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/pdf",
                "x-upsert": "true",
            },
            data=content,
            timeout=30,
        )
        resp.raise_for_status()
        return path
    except Exception:
        logger.exception("wa: failed to upload résumé to Supabase Storage")
        return None
