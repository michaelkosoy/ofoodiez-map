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
    # Nullable: a self-serve referral link curated by ops has no person behind it.
    user_id = db.Column(db.BigInteger, db.ForeignKey("wa_users.id"), nullable=True)
    company_id = db.Column(db.BigInteger, db.ForeignKey("wa_companies.id"), nullable=False)
    email = db.Column(db.Text)          # work email where applications are emailed (email method)
    referral_link = db.Column(db.Text)  # self-serve coded link auto-shared with candidates (link method)
    role_title = db.Column(db.Text)
    advocate_name = db.Column(db.Text)  # display name for a curated advocate with no bot user
    status = db.Column(db.Text, nullable=False, default="active")  # active|pending|inactive
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # One row per work email an advocate gives for a company (they can add a
        # few), so this is unique on (user, company, email) — not (user, company).
        db.Index("uq_wa_advocates_user_company_email",
                 "user_id", "company_id", "email", unique=True),
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


class WaApplication(db.Model):
    """A candidate's submitted application to a company."""
    __tablename__ = "wa_applications"

    id = _pk()
    candidate_user_id = db.Column(db.BigInteger, db.ForeignKey("wa_users.id"), nullable=False)
    company_id = db.Column(db.BigInteger, db.ForeignKey("wa_companies.id"), nullable=False)
    role_query = db.Column(db.Text)
    job_posting_url = db.Column(db.Text)
    job_description = db.Column(db.Text)     # free-text role details when no link is given
    resume_path = db.Column(db.Text)        # Supabase Storage object path (or a fallback ref)
    resume_filename = db.Column(db.Text)
    status = db.Column(db.Text, nullable=False, default="submitted")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<WaApplication {self.id} user={self.candidate_user_id} company={self.company_id}>"


class WaApplicationRecipient(db.Model):
    """Per-advocate delivery record for an application's notification email."""
    __tablename__ = "wa_application_recipients"

    id = _pk()
    application_id = db.Column(db.BigInteger, db.ForeignKey("wa_applications.id"), nullable=False)
    advocate_id = db.Column(db.BigInteger, db.ForeignKey("wa_advocates.id"), nullable=False)
    email = db.Column(db.Text)
    emailed_at = db.Column(db.DateTime)
    email_status = db.Column(db.Text)       # sent | pending | failed
    error = db.Column(db.Text)
    approval_token = db.Column(db.Text, unique=True)  # capability token in the advocate's "I referred them" link
    approved_at = db.Column(db.DateTime)              # set when the advocate confirms the referral
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<WaApplicationRecipient app={self.application_id} adv={self.advocate_id} {self.email_status}>"


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
