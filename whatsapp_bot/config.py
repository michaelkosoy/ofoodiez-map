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
    def WA_PUBLIC_BASE_URL(self):
        """Public origin for links we email out (e.g. the referral-approval link).
        Defaults to the host of TWILIO_WEBHOOK_URL so it tracks the deployment."""
        explicit = os.environ.get("WA_PUBLIC_BASE_URL")
        if explicit:
            return explicit.rstrip("/")
        url = self.TWILIO_WEBHOOK_URL or ""
        for suffix in ("/wa/webhook", "/webhook"):
            if url.endswith(suffix):
                return url[: -len(suffix)]
        return url.rstrip("/")

    @property
    def TWILIO_MESSAGING_SERVICE_SID(self):
        return os.environ.get("TWILIO_MESSAGING_SERVICE_SID")

    @property
    def TWILIO_WHATSAPP_FROM(self):
        # Sandbox shared sender (e.g. "whatsapp:+14155238886"). When set, outbound
        # uses this `from` number; otherwise it routes via the Messaging Service.
        return os.environ.get("TWILIO_WHATSAPP_FROM")

    @property
    def WA_CT_WELCOME(self):
        return os.environ.get("WA_CT_WELCOME")

    @property
    def WA_CT_BACK_TO_MENU(self):
        return os.environ.get("WA_CT_BACK_TO_MENU")

    @property
    def WA_CT_REGISTER_REVIEW(self):
        return os.environ.get("WA_CT_REGISTER_REVIEW")

    @property
    def WA_CT_PROMPT(self):
        # Reusable quick-reply template: body is {{1}} + a single "Back to Menu"
        # button (payload BACK_TO_MENU). Used by messaging.send_prompt so every
        # text prompt carries a back button.
        return os.environ.get("WA_CT_PROMPT")

    @property
    def WA_CT_EMPLOYEE_CONFIRM(self):
        return os.environ.get("WA_CT_EMPLOYEE_CONFIRM")

    @property
    def WA_CT_EMP_METHOD(self):
        # Optional quick-reply template (no variables) for the email-vs-link
        # choice: buttons EMP_METHOD_EMAIL / EMP_METHOD_LINK. Falls back to a
        # plain 1/2 text prompt when unset.
        return os.environ.get("WA_CT_EMP_METHOD")

    @property
    def WA_CT_EXPLORE_MORE(self):
        return os.environ.get("WA_CT_EXPLORE_MORE")

    # ---- Résumé storage (Supabase Storage) + advocate emails (SendGrid) ----
    @property
    def SUPABASE_URL(self):
        return os.environ.get("SUPABASE_URL")

    @property
    def SUPABASE_SERVICE_ROLE_KEY(self):
        return os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    @property
    def SUPABASE_RESUME_BUCKET(self):
        return os.environ.get("SUPABASE_RESUME_BUCKET", "wa-resumes")

    @property
    def SENDGRID_API_KEY(self):
        return os.environ.get("SENDGRID_API_KEY")

    @property
    def WA_FROM_EMAIL(self):
        return os.environ.get("WA_FROM_EMAIL")

    @property
    def WA_OPS_EMAIL(self):
        # Where "company not found / no advocates yet" requests are emailed.
        return os.environ.get("WA_OPS_EMAIL", "info@ofoodiez.com")

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
    def IDLE_RESET_MINUTES(self):
        # After this many minutes of inactivity, the next inbound message starts
        # a fresh conversation (personalised Welcome) instead of resuming.
        return int(os.environ.get("WA_IDLE_RESET_MINUTES", "30"))

    @property
    def MAX_RESULTS(self):
        return int(os.environ.get("WA_MAX_RESULTS", "5"))


WaConfig = _WaConfig()
