"""Configuration for the WhatsApp bot.

Values are read live from the environment on each access so they can be set
per-process (Render env in prod, `.env` locally) and overridden in tests via
``monkeypatch.setenv`` without re-importing anything.
"""
import os

# Pinned, exact public webhook URL. We validate Twilio signatures against this
# rather than reconstructing request.url, because there is no ProxyFix and
# Render/Cloudflare rewrite the scheme/host (see plan §6).
DEFAULT_WEBHOOK_URL = "https://ofoodiez-map.onrender.com/wa/webhook"


class _WaConfig:
    # ---- Twilio ----
    @property
    def TWILIO_AUTH_TOKEN(self):
        return os.environ.get("TWILIO_AUTH_TOKEN")

    @property
    def TWILIO_WEBHOOK_URL(self):
        return os.environ.get("TWILIO_WEBHOOK_URL", DEFAULT_WEBHOOK_URL)

    @property
    def TWILIO_ACCOUNT_SID(self):
        return os.environ.get("TWILIO_ACCOUNT_SID")

    @property
    def TWILIO_MESSAGING_SERVICE_SID(self):
        return os.environ.get("TWILIO_MESSAGING_SERVICE_SID")

    @property
    def WA_CT_WELCOME(self):
        return os.environ.get("WA_CT_WELCOME")

    @property
    def WA_CT_BACK_TO_MENU(self):
        return os.environ.get("WA_CT_BACK_TO_MENU")

    # ---- Behaviour thresholds (consumed by later PRs; centralised here) ----
    @property
    def MAX_BODY_LENGTH(self):
        return int(os.environ.get("WA_MAX_BODY_LENGTH", "2000"))

    @property
    def RATE_LIMIT_PER_MIN(self):
        return int(os.environ.get("WA_RATE_LIMIT_PER_MIN", "10"))

    @property
    def MAX_PENDING_PER_USER(self):
        return int(os.environ.get("WA_MAX_PENDING_PER_USER", "5"))

    @property
    def MAX_SUBMISSIONS_PER_DAY(self):
        return int(os.environ.get("WA_MAX_SUBMISSIONS_PER_DAY", "20"))

    @property
    def SELECTION_TTL_MINUTES(self):
        return int(os.environ.get("WA_SELECTION_TTL_MINUTES", "30"))

    @property
    def MAX_RESULTS(self):
        return int(os.environ.get("WA_MAX_RESULTS", "5"))


WaConfig = _WaConfig()
