"""SQLAlchemy models for the WhatsApp referral bot.

These mirror the one-time Supabase SQL schema (docs/whatsapp-referral-bot-plan.md
§4) and hang off the single shared ``db`` defined in
``database.models``. In production the wa_ tables are created by
that SQL script (with RLS + indexes); ``db.create_all()`` only materialises them
in tests (sqlite).
"""
from datetime import datetime

from database.models import db


def _pk():
    """A bigint identity primary key that also autoincrements on SQLite.

    SQLite only treats a column whose declared type is exactly ``INTEGER`` as an
    alias for ROWID (and therefore autoincrements it). A bare ``BIGINT`` primary
    key would not autoincrement on SQLite, breaking the in-memory test DB. So we
    use ``INTEGER`` on sqlite and ``BIGINT`` everywhere else (Postgres identity).
    This mirrors the plan's dual-dialect handling of the partial unique index.
    """
    return db.Column(db.BigInteger().with_variant(db.Integer(), "sqlite"), primary_key=True)


class WaCompany(db.Model):
    __tablename__ = "wa_companies"

    id = _pk()
    name = db.Column(db.Text, nullable=False)
    normalized_name = db.Column(db.Text, nullable=False, unique=True)  # lower(trim(name))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<WaCompany {self.name!r}>"


class WaAdvocate(db.Model):
    """An employee who will receive/refer candidate applications for a company."""
    __tablename__ = "wa_advocates"

    id = _pk()
    user_id = db.Column(db.BigInteger, db.ForeignKey("wa_users.id"), nullable=False)
    company_id = db.Column(db.BigInteger, db.ForeignKey("wa_companies.id"), nullable=False)
    role_title = db.Column(db.Text)
    status = db.Column(db.Text, nullable=False, default="active")  # active|pending|inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index("uq_wa_advocates_user_company", "user_id", "company_id", unique=True),
    )

    def __repr__(self):
        return f"<WaAdvocate user={self.user_id} company={self.company_id}>"


class WaCompanyRequest(db.Model):
    """A candidate search for an unknown / no-advocate company — the ops
    backfill queue that powers the 'we'll add it, check back' promise."""
    __tablename__ = "wa_company_requests"

    id = _pk()
    candidate_user_id = db.Column(db.BigInteger, db.ForeignKey("wa_users.id"), nullable=False)
    company_name_raw = db.Column(db.Text, nullable=False)
    normalized_name = db.Column(db.Text)
    resolved_company_id = db.Column(db.BigInteger, db.ForeignKey("wa_companies.id"))
    reason = db.Column(db.Text, nullable=False)  # unknown_company | no_advocates
    status = db.Column(db.Text, nullable=False, default="open")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<WaCompanyRequest {self.company_name_raw!r} {self.reason}>"


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

    @property
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


class WaInboundMessage(db.Model):
    """The webhook-event log AND the idempotency key store.

    ``message_sid`` is UNIQUE: claiming it (INSERT + commit) before any side
    effect is what makes the webhook idempotent.
    """

    __tablename__ = "wa_inbound_messages"

    id = _pk()
    message_sid = db.Column(db.Text, nullable=False, unique=True)  # Twilio MessageSid
    from_phone = db.Column(db.Text, nullable=False)
    profile_name = db.Column(db.Text)
    body = db.Column(db.Text)
    num_media = db.Column(db.Integer, nullable=False, default=0)
    parsed_command = db.Column(db.Text)  # help|add|select|search|ratelimited|error
    response_summary = db.Column(db.Text)
    processing_ms = db.Column(db.Integer)
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<WaInboundMessage {self.message_sid}>"
