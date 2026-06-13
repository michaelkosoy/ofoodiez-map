"""Pytest fixtures for the WhatsApp bot.

Builds an isolated Flask app bound to an in-memory SQLite database, wires the
shared `db` (from instagram_automation) and the `wa_bp` blueprint, and creates
the tables via `create_all` (sqlite only — production uses the one-time Supabase
SQL script described in docs/whatsapp-referral-bot-plan.md §4).
"""
import pytest
from flask import Flask
from sqlalchemy.pool import StaticPool
from twilio.request_validator import RequestValidator

# The test app is configured with these; the `sign` fixture signs against them.
TEST_AUTH_TOKEN = "test_auth_token_123"
TEST_WEBHOOK_URL = "https://example.com/wa/webhook"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TEST_AUTH_TOKEN)
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", TEST_WEBHOOK_URL)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_MESSAGING_SERVICE_SID", "MG_test")
    monkeypatch.setenv("WA_CT_WELCOME", "HX_welcome")
    monkeypatch.setenv("WA_CT_BACK_TO_MENU", "HX_back")

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # Keep one shared connection so the test client and post-request
        # assertions see the same in-memory database.
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        },
    )

    from instagram_automation.database import db
    from whatsapp_bot import init_app as init_wa_bot

    init_wa_bot(flask_app)  # registers wa_bp + imports models; does NOT init db
    db.init_app(flask_app)

    with flask_app.app_context():
        db.create_all()
        try:
            yield flask_app
        finally:
            db.session.remove()
            db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sign():
    """Return a helper that builds a valid X-Twilio-Signature header for the
    given POST params, matching the token/URL the test app is configured with."""

    def _sign(params):
        signature = RequestValidator(TEST_AUTH_TOKEN).compute_signature(
            TEST_WEBHOOK_URL, params
        )
        return {"X-Twilio-Signature": signature}

    return _sign


@pytest.fixture
def mock_twilio(monkeypatch):
    sent = []

    class _FakeMessages:
        def create(self, **kwargs):
            sent.append(kwargs)
            return type("Msg", (), {"sid": f"SM_fake_{len(sent)}", "status": "queued"})()

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = _FakeMessages()

    monkeypatch.setattr("whatsapp_bot.messaging.Client", _FakeClient)
    return sent
