# Ofoodiez Referrals Bot — Foundation (Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the messaging + state-machine foundation for the candidate↔advocate WhatsApp bot: a button-driven Welcome menu that routes to one of three flows and a working "Back to Menu" reset — replacing PR1's static TwiML help reply.

**Architecture:** Reuse PR1's signed/idempotent/audited `/wa/webhook`, but the reply path changes: the webhook now acknowledges with an empty 200 and replies are sent via the **Twilio REST Messages API** (text or Content-template buttons) through a Messaging Service. Conversation state is a per-user row (`wa_conversations`) so the bot is stateful across requests/restarts. Three isolated units — messaging layer, state machine/router, flow handlers — keep logic unit-testable without network.

**Tech Stack:** Flask 3.1 + Flask-SQLAlchemy (shared `db`), `twilio` SDK (REST `Client` + Content templates), Supabase Postgres (prod) / sqlite (tests), pytest. No new runtime deps.

**Scope note:** This is **Plan 1 of a sequence** derived from `docs/superpowers/specs/2026-06-13-ofoodiez-referrals-bot-design.md`. It implements the spec's **Phase 0 (spike)** and **Phase A (foundation)** only. Phases B–G (registration, candidate, submission/delivery, employee, contact, hardening) become their own plans. This plan defines only the tables Phase A consumes; later phases add their tables to `schema.sql` and `models.py` when their consumers exist (the PR1 `create_all`-can't-migrate lesson).

---

## Operator prerequisites (do before Task 6 can be tested live; not needed for unit/integration tests)

1. In Twilio Console → Content Template Builder, create two **quick-reply** templates:
   - **Welcome** — body (see copy below), 3 buttons with payloads `PATH_CANDIDATE`, `PATH_EMPLOYEE`, `PATH_CONTACT`. Copy its `ContentSid`.
   - **Back to Menu** — body "Tap below to start over.", 1 button payload `BACK_TO_MENU`. Copy its `ContentSid`.
2. Confirm a sender (the sandbox number for now) is attached to your Messaging Service; note the **Messaging Service SID**.
3. Set env vars (Render + local `.env`): `TWILIO_ACCOUNT_SID`, `TWILIO_MESSAGING_SERVICE_SID`, `WA_CT_WELCOME`, `WA_CT_BACK_TO_MENU`. (`TWILIO_AUTH_TOKEN`, `TWILIO_WEBHOOK_URL` already set.)
4. **Sandbox spike:** point the sandbox "When a message comes in" at the webhook (local ngrok per `run_wa_local.py`, or prod), text the sandbox, and confirm the Welcome buttons render and a tap returns `ButtonPayload=PATH_CANDIDATE` to the webhook (check `wa_inbound_messages`). This de-risks the whole button approach before building flows.

Welcome copy (English, v1):
```
Welcome to Ofoodiez Referrals — your shortcut to your dream job in tech. We connect you straight to people on the inside. Pick a lane:
```

---

## File structure (this plan)

- Modify `whatsapp_bot/models.py` — drop `WaReferralLink`; enrich `WaUser`; add `WaConversation`, `WaOutboundMessage`.
- Modify `whatsapp_bot/schema.sql` — same changes in DDL.
- Modify `whatsapp_bot/config.py` — add `TWILIO_ACCOUNT_SID`, `TWILIO_MESSAGING_SERVICE_SID`, `WA_CT_WELCOME`, `WA_CT_BACK_TO_MENU`.
- Create `whatsapp_bot/messaging.py` — `send_text`, `send_buttons` (only code that calls Twilio outbound) + outbound log.
- Create `whatsapp_bot/conversation.py` — user get-or-create + state load/save/reset.
- Create `whatsapp_bot/router.py` — `handle(inbound)` dispatch + Welcome flow + Back-to-Menu.
- Modify `whatsapp_bot/webhooks.py` — replace the static-help reply with parse-inbound → `router.handle` → empty 200.
- Modify `tests/conftest.py` — set the new env vars; add a `mock_twilio` autouse fixture.
- Create `tests/whatsapp_bot/test_messaging.py`, `test_conversation.py`, `test_router.py`; extend `tests/whatsapp_bot/test_webhook.py`.

---

## Task 1: Data model + schema

**Files:**
- Modify: `whatsapp_bot/models.py`
- Modify: `whatsapp_bot/schema.sql`
- Test: `tests/whatsapp_bot/test_models.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/whatsapp_bot/test_models.py`:
```python
from datetime import datetime
from instagram_automation.database import db
from whatsapp_bot.models import WaUser, WaConversation, WaOutboundMessage


def test_user_has_registration_fields(app):
    with app.app_context():
        u = WaUser(phone="+972500000001", profile_name="Ada",
                   first_name="Ada", last_name="Lovelace",
                   email="ada@example.com", terms_accepted_at=datetime.utcnow())
        db.session.add(u); db.session.commit()
        got = WaUser.query.filter_by(phone="+972500000001").one()
        assert got.first_name == "Ada"
        assert got.email == "ada@example.com"
        assert got.terms_accepted_at is not None


def test_conversation_is_one_per_user(app):
    with app.app_context():
        u = WaUser(phone="+972500000002"); db.session.add(u); db.session.commit()
        c = WaConversation(user_id=u.id, flow="candidate", step="start", data={"x": 1})
        db.session.add(c); db.session.commit()
        got = WaConversation.query.filter_by(user_id=u.id).one()
        assert got.flow == "candidate"
        assert got.data == {"x": 1}


def test_outbound_message_row(app):
    with app.app_context():
        o = WaOutboundMessage(to_phone="+972500000003", body="hi",
                              twilio_sid="SM123", status="queued")
        db.session.add(o); db.session.commit()
        assert WaOutboundMessage.query.count() == 1


def test_referral_link_model_removed():
    import whatsapp_bot.models as m
    assert not hasattr(m, "WaReferralLink")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_models.py -q`
Expected: FAIL — `ImportError: cannot import name 'WaConversation'` (and `WaReferralLink` still present).

- [ ] **Step 3: Edit `whatsapp_bot/models.py`**

Remove the `WaReferralLink` class entirely. Replace the `WaUser` class body and add the two new models (keep `_pk()`, `WaCompany`, `WaInboundMessage` as they are):
```python
class WaUser(db.Model):
    __tablename__ = "wa_users"

    id = _pk()
    phone = db.Column(db.Text, nullable=False, unique=True)  # E.164, no 'whatsapp:' prefix
    profile_name = db.Column(db.Text)
    first_name = db.Column(db.Text)
    last_name = db.Column(db.Text)
    email = db.Column(db.Text)
    terms_accepted_at = db.Column(db.DateTime)
    last_language = db.Column(db.Text, nullable=False, default="en")
    is_blocked = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def is_registered(self):
        return bool(self.first_name and self.email)

    def __repr__(self):
        return f"<WaUser {self.phone}>"


class WaConversation(db.Model):
    """Live conversation state, one row per user."""
    __tablename__ = "wa_conversations"

    id = _pk()
    user_id = db.Column(db.BigInteger, db.ForeignKey("wa_users.id"), nullable=False, unique=True)
    flow = db.Column(db.Text)          # candidate | employee | contact | None
    step = db.Column(db.Text)
    data = db.Column(db.JSON, default=dict)   # reassign whole dict; never mutate in place
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<WaConversation user={self.user_id} {self.flow}/{self.step}>"


class WaOutboundMessage(db.Model):
    """Log of every outbound REST send (replies are async REST, not TwiML)."""
    __tablename__ = "wa_outbound_messages"

    id = _pk()
    to_phone = db.Column(db.Text, nullable=False)
    body = db.Column(db.Text)
    content_sid = db.Column(db.Text)
    twilio_sid = db.Column(db.Text)
    status = db.Column(db.Text)
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<WaOutboundMessage to={self.to_phone} {self.twilio_sid}>"
```

- [ ] **Step 4: Edit `whatsapp_bot/schema.sql`**

In Part 1, delete the entire `wa_referral_links` block (table + its three indexes). Replace the `wa_users` `create table` with the columns below, and add the two new tables. Add their RLS lines to the RLS block; remove the `wa_referral_links` RLS line.
```sql
create table if not exists public.wa_users (
    id                bigint generated by default as identity primary key,
    phone             text not null unique,
    profile_name      text,
    first_name        text,
    last_name         text,
    email             text,
    terms_accepted_at timestamptz,
    last_language     text not null default 'en' check (last_language in ('en','he')),
    is_blocked        boolean not null default false,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

create table if not exists public.wa_conversations (
    id          bigint generated by default as identity primary key,
    user_id     bigint not null unique references public.wa_users(id),
    flow        text,
    step        text,
    data        jsonb not null default '{}'::jsonb,
    updated_at  timestamptz not null default now()
);

create table if not exists public.wa_outbound_messages (
    id          bigint generated by default as identity primary key,
    to_phone    text not null,
    body        text,
    content_sid text,
    twilio_sid  text,
    status      text,
    error       text,
    created_at  timestamptz not null default now()
);
```
RLS block (replace the `wa_referral_links` line):
```sql
alter table public.wa_conversations    enable row level security;
alter table public.wa_outbound_messages enable row level security;
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_models.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add whatsapp_bot/models.py whatsapp_bot/schema.sql tests/whatsapp_bot/test_models.py
git commit -m "feat(whatsapp_bot): foundation data model (users+conversations+outbound), drop referral links"
```

---

## Task 2: Config additions

**Files:**
- Modify: `whatsapp_bot/config.py`
- Test: `tests/whatsapp_bot/test_config.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/whatsapp_bot/test_config.py`:
```python
from whatsapp_bot.config import WaConfig


def test_twilio_rest_config_reads_env(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_MESSAGING_SERVICE_SID", "MG_test")
    monkeypatch.setenv("WA_CT_WELCOME", "HX_welcome")
    monkeypatch.setenv("WA_CT_BACK_TO_MENU", "HX_back")
    assert WaConfig.TWILIO_ACCOUNT_SID == "AC_test"
    assert WaConfig.TWILIO_MESSAGING_SERVICE_SID == "MG_test"
    assert WaConfig.WA_CT_WELCOME == "HX_welcome"
    assert WaConfig.WA_CT_BACK_TO_MENU == "HX_back"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_config.py -q`
Expected: FAIL — `AttributeError: 'WaConfig' has no attribute 'TWILIO_ACCOUNT_SID'`.

- [ ] **Step 3: Add properties to `_WaConfig` in `whatsapp_bot/config.py`**

Inside the `_WaConfig` class (next to `TWILIO_AUTH_TOKEN`):
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_bot/config.py tests/whatsapp_bot/test_config.py
git commit -m "feat(whatsapp_bot): config for Twilio REST + Content SIDs"
```

---

## Task 3: Messaging layer (outbound)

**Files:**
- Create: `whatsapp_bot/messaging.py`
- Modify: `tests/conftest.py` (add `mock_twilio` fixture + new env vars)
- Test: `tests/whatsapp_bot/test_messaging.py` (create)

- [ ] **Step 1: Add the test env vars + a `mock_twilio` fixture to `tests/conftest.py`**

In the `app` fixture, after the existing `monkeypatch.setenv("TWILIO_WEBHOOK_URL", ...)` line, add:
```python
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_test")
    monkeypatch.setenv("TWILIO_MESSAGING_SERVICE_SID", "MG_test")
    monkeypatch.setenv("WA_CT_WELCOME", "HX_welcome")
    monkeypatch.setenv("WA_CT_BACK_TO_MENU", "HX_back")
```
Add this fixture at the end of the file (records calls, returns fake message SIDs, never hits the network):
```python
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
```

- [ ] **Step 2: Write the failing test**

Create `tests/whatsapp_bot/test_messaging.py`:
```python
import json
from whatsapp_bot import messaging
from whatsapp_bot.models import WaOutboundMessage


def test_send_text_calls_twilio_and_logs(app, mock_twilio):
    with app.app_context():
        sid = messaging.send_text("+972500000010", "hello there")
        assert sid.startswith("SM_fake_")
        call = mock_twilio[0]
        assert call["to"] == "whatsapp:+972500000010"
        assert call["body"] == "hello there"
        assert call["messaging_service_sid"] == "MG_test"
        row = WaOutboundMessage.query.one()
        assert row.body == "hello there"
        assert row.twilio_sid == sid


def test_send_buttons_uses_content_sid_and_variables(app, mock_twilio):
    with app.app_context():
        messaging.send_buttons("+972500000011", "HX_welcome", {"1": "Ofoodiez"})
        call = mock_twilio[0]
        assert call["content_sid"] == "HX_welcome"
        assert json.loads(call["content_variables"]) == {"1": "Ofoodiez"}
        assert WaOutboundMessage.query.one().content_sid == "HX_welcome"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_messaging.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'whatsapp_bot.messaging'`.

- [ ] **Step 4: Create `whatsapp_bot/messaging.py`**

```python
"""Outbound messaging — the only module that calls the Twilio REST API.

Replies are sent here (not via TwiML) because WhatsApp interactive buttons
require the Content API. Every send is logged to wa_outbound_messages.
"""
import json
import logging

from twilio.rest import Client

from instagram_automation.database import db

from .config import WaConfig
from .models import WaOutboundMessage

logger = logging.getLogger("whatsapp_bot")


def _client():
    return Client(WaConfig.TWILIO_ACCOUNT_SID, WaConfig.TWILIO_AUTH_TOKEN)


def _to(phone):
    return phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"


def _log(to_phone, twilio_sid=None, status=None, body=None, content_sid=None, error=None):
    row = WaOutboundMessage(
        to_phone=to_phone, body=body, content_sid=content_sid,
        twilio_sid=twilio_sid, status=status, error=error,
    )
    db.session.add(row)
    db.session.commit()


def send_text(to_phone, body):
    try:
        msg = _client().messages.create(
            messaging_service_sid=WaConfig.TWILIO_MESSAGING_SERVICE_SID,
            to=_to(to_phone), body=body,
        )
        _log(to_phone, twilio_sid=msg.sid, status=getattr(msg, "status", None), body=body)
        return msg.sid
    except Exception as exc:
        logger.exception("wa send_text failed to %s", to_phone)
        _log(to_phone, body=body, error=str(exc))
        raise


def send_buttons(to_phone, content_sid, variables=None):
    try:
        msg = _client().messages.create(
            messaging_service_sid=WaConfig.TWILIO_MESSAGING_SERVICE_SID,
            to=_to(to_phone), content_sid=content_sid,
            content_variables=json.dumps(variables or {}),
        )
        _log(to_phone, twilio_sid=msg.sid, status=getattr(msg, "status", None), content_sid=content_sid)
        return msg.sid
    except Exception as exc:
        logger.exception("wa send_buttons failed to %s", to_phone)
        _log(to_phone, content_sid=content_sid, error=str(exc))
        raise
```

- [ ] **Step 5: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_messaging.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add whatsapp_bot/messaging.py tests/conftest.py tests/whatsapp_bot/test_messaging.py
git commit -m "feat(whatsapp_bot): outbound messaging layer (send_text/send_buttons) + outbound log"
```

---

## Task 4: Conversation state

**Files:**
- Create: `whatsapp_bot/conversation.py`
- Test: `tests/whatsapp_bot/test_conversation.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/whatsapp_bot/test_conversation.py`:
```python
from whatsapp_bot import conversation
from whatsapp_bot.models import WaUser, WaConversation


def test_get_or_create_user_is_idempotent(app):
    with app.app_context():
        u1 = conversation.get_or_create_user("+972500000020", "Grace")
        u2 = conversation.get_or_create_user("+972500000020", "Grace")
        assert u1.id == u2.id
        assert WaUser.query.filter_by(phone="+972500000020").count() == 1
        assert u1.profile_name == "Grace"


def test_state_lifecycle(app):
    with app.app_context():
        u = conversation.get_or_create_user("+972500000021")
        conv = conversation.get_state(u)
        assert conv.flow is None and conv.step is None
        conversation.set_state(conv, "candidate", "cand_company", {"company": "Intuit"})
        again = conversation.get_state(u)
        assert again.flow == "candidate"
        assert again.step == "cand_company"
        assert again.data == {"company": "Intuit"}
        conversation.reset_state(conv)
        assert conversation.get_state(u).flow is None
        assert WaConversation.query.filter_by(user_id=u.id).count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_conversation.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'whatsapp_bot.conversation'`.

- [ ] **Step 3: Create `whatsapp_bot/conversation.py`**

```python
"""User identity + per-user conversation state (DB-backed state machine store)."""
from datetime import datetime

from instagram_automation.database import db

from .models import WaConversation, WaUser


def get_or_create_user(phone, profile_name=None):
    user = WaUser.query.filter_by(phone=phone).first()
    if user is None:
        user = WaUser(phone=phone, profile_name=profile_name)
        db.session.add(user)
        db.session.commit()
    elif profile_name and user.profile_name != profile_name:
        user.profile_name = profile_name
        db.session.commit()
    return user


def get_state(user):
    conv = WaConversation.query.filter_by(user_id=user.id).first()
    if conv is None:
        conv = WaConversation(user_id=user.id, flow=None, step=None, data={})
        db.session.add(conv)
        db.session.commit()
    return conv


def set_state(conv, flow, step, data=None):
    conv.flow = flow
    conv.step = step
    if data is not None:
        conv.data = data  # whole-dict reassignment; JSON in-place mutation isn't tracked
    conv.updated_at = datetime.utcnow()
    db.session.commit()


def reset_state(conv):
    set_state(conv, None, None, {})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_conversation.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add whatsapp_bot/conversation.py tests/whatsapp_bot/test_conversation.py
git commit -m "feat(whatsapp_bot): conversation state (user get-or-create + state load/save/reset)"
```

---

## Task 5: Router + Welcome flow

**Files:**
- Create: `whatsapp_bot/router.py`
- Test: `tests/whatsapp_bot/test_router.py` (create)

`router.handle(inbound)` is the dispatch entry. `inbound` is a dict:
`{"phone", "profile_name", "body", "button_payload", "num_media", "media_url", "media_content_type"}`.
It returns a short string label for the audit row (`parsed_command`).

- [ ] **Step 1: Write the failing test**

Create `tests/whatsapp_bot/test_router.py`:
```python
from whatsapp_bot import router, conversation
from whatsapp_bot.models import WaConversation


def _inbound(**kw):
    base = {"phone": "+972500000030", "profile_name": "Alan", "body": "",
            "button_payload": None, "num_media": 0,
            "media_url": None, "media_content_type": None}
    base.update(kw)
    return base


def test_first_contact_sends_welcome(app, mock_twilio):
    with app.app_context():
        label = router.handle(_inbound(body="hi"))
        assert label == "welcome"
        assert mock_twilio[0]["content_sid"] == "HX_welcome"


def test_candidate_button_enters_candidate_flow(app, mock_twilio):
    with app.app_context():
        router.handle(_inbound(body="hi"))            # welcome first
        label = router.handle(_inbound(button_payload="PATH_CANDIDATE"))
        assert label == "enter_candidate"
        u = conversation.get_or_create_user("+972500000030")
        assert conversation.get_state(u).flow == "candidate"
        # a follow-up message was sent (the path stub)
        assert any("Candidate" in c.get("body", "") for c in mock_twilio)


def test_back_to_menu_resets(app, mock_twilio):
    with app.app_context():
        router.handle(_inbound(body="hi"))
        router.handle(_inbound(button_payload="PATH_EMPLOYEE"))
        label = router.handle(_inbound(button_payload="BACK_TO_MENU"))
        assert label == "welcome"
        u = conversation.get_or_create_user("+972500000030")
        assert conversation.get_state(u).flow is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_router.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'whatsapp_bot.router'`.

- [ ] **Step 3: Create `whatsapp_bot/router.py`**

```python
"""Dispatch + Welcome flow.

Phase A only routes the Welcome menu and Back-to-Menu. The three path
selections set the flow and reply with a transitional stub; Phases B–F replace
those stubs with the real registration/candidate/employee/contact handlers.
"""
import logging

from . import conversation, messaging
from .config import WaConfig

logger = logging.getLogger("whatsapp_bot")

RESET_KEYWORDS = {"menu", "back", "restart", "hi", "hello", "start"}

# Transitional stubs (replaced in Phases B–F).
_PATH_STUBS = {
    "PATH_CANDIDATE": ("candidate", "You're in the Candidate flow! (coming soon)"),
    "PATH_EMPLOYEE": ("employee", "You're in the Employee flow! (coming soon)"),
    "PATH_CONTACT": ("contact", "You're in Contact Us! (coming soon)"),
}


def handle(inbound):
    user = conversation.get_or_create_user(inbound["phone"], inbound.get("profile_name"))
    conv = conversation.get_state(user)
    payload = inbound.get("button_payload")
    text = (inbound.get("body") or "").strip()

    # Global reset: explicit Back-to-Menu button, reset keyword, or no active flow.
    if payload == "BACK_TO_MENU" or text.lower() in RESET_KEYWORDS or conv.flow is None:
        return _welcome(user, conv)

    if payload in _PATH_STUBS:
        flow, stub = _PATH_STUBS[payload]
        conversation.set_state(conv, flow, "start", {})
        messaging.send_text(user.phone, stub)
        return f"enter_{flow}"

    # Anything unrecognized in Phase A: re-show the menu.
    return _welcome(user, conv)


def _welcome(user, conv):
    conversation.reset_state(conv)
    messaging.send_buttons(user.phone, WaConfig.WA_CT_WELCOME)
    return "welcome"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_router.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add whatsapp_bot/router.py tests/whatsapp_bot/test_router.py
git commit -m "feat(whatsapp_bot): router dispatch + Welcome menu + Back-to-Menu reset"
```

---

## Task 6: Wire the router into the webhook

**Files:**
- Modify: `whatsapp_bot/webhooks.py`
- Test: `tests/whatsapp_bot/test_webhook.py` (extend; the PR1 signature/idempotency tests stay)

The webhook keeps PR1's verify → claim → audit → finally(timing) shape. We replace the static-help reply with: build the `inbound` dict (incl. `ButtonPayload`), call `router.handle`, store its label as `parsed_command`, and return an **empty** TwiML 200 (replies already went out via REST inside the router).

- [ ] **Step 1: Update the PR1 help-reply assertion + add a button test in `tests/whatsapp_bot/test_webhook.py`**

The existing `test_valid_signed_message_returns_200_with_message` asserted a `<Message>` help reply, which no longer happens (replies go via REST). Replace that test with:
```python
def test_valid_signed_message_acks_and_sends_welcome(client, app, sign, mock_twilio):
    params = _msg(Body="hi")
    resp = client.post("/wa/webhook", data=params, headers=sign(params))
    assert resp.status_code == 200
    assert "<Message>" not in resp.get_data(as_text=True)   # empty TwiML ack
    assert mock_twilio[0]["content_sid"] == "HX_welcome"    # welcome sent via REST


def test_button_payload_is_routed(client, app, sign, mock_twilio):
    params = _msg(MessageSid="SMbtn0000000000000000000000000001", Body="")
    params["ButtonPayload"] = "PATH_CANDIDATE"
    resp = client.post("/wa/webhook", data=params, headers=sign(params))
    assert resp.status_code == 200
    from whatsapp_bot.models import WaInboundMessage
    with app.app_context():
        row = WaInboundMessage.query.filter_by(
            message_sid="SMbtn0000000000000000000000000001").one()
        assert row.parsed_command == "enter_candidate"
```
Keep `test_tampered_signature_is_rejected_403`, `test_missing_auth_token_fails_closed_403`, `test_duplicate_message_sid_is_processed_once`, and `test_audit_row_is_populated` — but in `test_audit_row_is_populated`, change the `parsed_command` assertion from `"help"` to `"welcome"`, and add the `mock_twilio` fixture argument to its signature so no real send happens.

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_webhook.py -q`
Expected: FAIL — welcome/button assertions fail (`parsed_command` is still `"help"`; no `content_sid` send).

- [ ] **Step 3: Edit `whatsapp_bot/webhooks.py`**

Replace the imports of `HELP`/`ERROR` usage and the "Handle the message" block. Update imports near the top:
```python
from . import wa_bp, router
from .config import WaConfig
from .copy import ERROR
from .models import WaInboundMessage
```
Replace the section that built the help reply (the block starting `# 3. Handle the message...` through the `_twiml(reply)` return at the end of `webhook()`) with:
```python
    # 3. Route to the conversation state machine. Replies are sent via REST
    #    inside the router; the webhook just acknowledges with empty TwiML.
    parsed_command = None
    error_text = None
    try:
        inbound = {
            "phone": from_phone,
            "profile_name": profile_name,
            "body": body,
            "button_payload": form.get("ButtonPayload"),
            "num_media": num_media,
            "media_url": form.get("MediaUrl0"),
            "media_content_type": form.get("MediaContentType0"),
        }
        parsed_command = router.handle(inbound)
    except Exception as exc:
        logger.exception("wa webhook: handler error for sid %s", message_sid)
        parsed_command = "error"
        error_text = str(exc)
        try:
            messaging.send_text(from_phone, ERROR["en"])
        except Exception:
            logger.exception("wa webhook: failed to send error reply")
    finally:
        audit.parsed_command = parsed_command
        audit.response_summary = (parsed_command or "")[:200]
        audit.processing_ms = int((time.monotonic() - started) * 1000)
        audit.error = error_text
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("wa webhook: failed to update audit row for sid %s", message_sid)

    return _twiml("")  # empty 200 ack; the reply already went out via REST
```
Add `from . import messaging` to the imports (used in the except branch). Keep `_twiml`, `_strip_whatsapp_prefix`, `_verify_twilio_signature` unchanged. The `HELP` import and `_detect_language`/lang logic are gone (already removed in PR1); remove the now-unused `HELP` import if present.

- [ ] **Step 4: Run the full webhook test file**

Run: `./venv/bin/python -m pytest tests/whatsapp_bot/test_webhook.py -q`
Expected: PASS (all webhook tests, incl. signature/idempotency, green).

- [ ] **Step 5: Run the whole suite**

Run: `./venv/bin/python -m pytest -q`
Expected: PASS (all tests across files).

- [ ] **Step 6: Commit**

```bash
git add whatsapp_bot/webhooks.py tests/whatsapp_bot/test_webhook.py
git commit -m "feat(whatsapp_bot): route webhook to state machine; reply via REST (empty TwiML ack)"
```

---

## Task 7: Schema migration + live sandbox verification (manual)

**Files:** none (operational).

- [ ] **Step 1: Apply the schema in Supabase**

If you have NOT yet run the PR1 `schema.sql`: run the current `whatsapp_bot/schema.sql` (Part 1) in the Supabase SQL editor.
If you ALREADY ran the PR1 version (with `wa_referral_links`): run only the deltas:
```sql
drop table if exists public.wa_referral_links;
alter table public.wa_users add column if not exists first_name text;
alter table public.wa_users add column if not exists last_name text;
alter table public.wa_users add column if not exists email text;
alter table public.wa_users add column if not exists terms_accepted_at timestamptz;
alter table public.wa_users drop column if exists last_results;
alter table public.wa_users drop column if exists last_results_at;
-- then create wa_conversations + wa_outbound_messages (copy their CREATE + RLS from schema.sql)
```

- [ ] **Step 2: Set env vars** `TWILIO_ACCOUNT_SID`, `TWILIO_MESSAGING_SERVICE_SID`, `WA_CT_WELCOME`, `WA_CT_BACK_TO_MENU` in Render (and local `.env`).

- [ ] **Step 3: Local sandbox test** — run `./venv/bin/python run_wa_local.py` + ngrok, point the sandbox webhook at it, text the sandbox: confirm the Welcome buttons appear, tapping **Candidate** replies with the stub, and "menu" returns the Welcome. Confirm rows in `wa_inbound_messages` (`parsed_command` = welcome/enter_candidate) and `wa_outbound_messages`.

- [ ] **Step 4: Commit any env/docs notes** (if you keep a runbook).

---

## Self-review (done by plan author)

- **Spec coverage (Phase A scope):** messaging layer ✓ (Task 3), state machine + `wa_conversations` ✓ (Tasks 1, 4), Welcome + routing + Back-to-Menu ✓ (Task 5), webhook reply-via-REST ✓ (Task 6), data-model revision incl. dropping `wa_referral_links` ✓ (Task 1), config/env ✓ (Task 2), RLS in `schema.sql` ✓ (Task 1), sandbox spike ✓ (prereqs + Task 7). Phases B–G are intentionally out of scope (separate plans).
- **Placeholder scan:** the only stubs are the three "coming soon" path messages in `router.py`, explicitly transitional and replaced in Phases B–F — not plan placeholders. No TBD/TODO steps.
- **Type/name consistency:** `router.handle(inbound)` returns the `parsed_command` label used in Task 6's webhook + audit assertions; `messaging.send_text/send_buttons`, `conversation.get_or_create_user/get_state/set_state/reset_state`, `WaConfig.WA_CT_WELCOME` names match across tasks; `mock_twilio` patches `whatsapp_bot.messaging.Client` (the import site).
- **Idempotency preserved:** Task 6 keeps PR1's claim-before-side-effect; a duplicate `MessageSid` returns the empty ack before `router.handle`, so no duplicate REST sends.
