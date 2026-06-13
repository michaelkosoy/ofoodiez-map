"""SQLAlchemy models for the WhatsApp referral bot.

These mirror the one-time Supabase SQL schema (docs/whatsapp-referral-bot-plan.md
§4) and hang off the single shared ``db`` defined in
``instagram_automation.database``. In production the wa_ tables are created by
that SQL script (with RLS + indexes); ``db.create_all()`` only materialises them
in tests (sqlite).
"""
from datetime import datetime

from instagram_automation.database import db


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


class WaUser(db.Model):
    __tablename__ = "wa_users"

    id = _pk()
    phone = db.Column(db.Text, nullable=False, unique=True)  # E.164, no 'whatsapp:' prefix
    profile_name = db.Column(db.Text)
    last_language = db.Column(db.Text, nullable=False, default="en")
    message_count = db.Column(db.Integer, nullable=False, default=0)
    is_blocked = db.Column(db.Boolean, nullable=False, default=False)
    last_results = db.Column(db.JSON)  # array of link ids; reassign whole list, never mutate in place
    last_results_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<WaUser {self.phone}>"


class WaReferralLink(db.Model):
    __tablename__ = "wa_referral_links"

    id = _pk()
    company_id = db.Column(db.BigInteger, db.ForeignKey("wa_companies.id"), nullable=False)
    submitter_user_id = db.Column(db.BigInteger, db.ForeignKey("wa_users.id"))
    submitter_display = db.Column(db.Text)  # first word of submitter's ProfileName
    role_title = db.Column(db.Text)
    url = db.Column(db.Text, nullable=False)  # cleaned, as shown to users
    url_canonical = db.Column(db.Text, nullable=False)  # for dedup
    status = db.Column(db.Text, nullable=False, default="pending")  # pending|approved|rejected|expired
    rejection_reason = db.Column(db.Text)
    times_sent = db.Column(db.Integer, nullable=False, default=0)
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Dedup among LIVE rows only: re-submitting a previously rejected/expired URL
    # is allowed. Both dialect `_where` clauses are supplied so the partial index
    # behaves identically on sqlite (tests) and postgres (prod) — see plan §4.
    __table_args__ = (
        db.Index(
            "uq_wa_links_company_url_active",
            "company_id",
            "url_canonical",
            unique=True,
            postgresql_where=db.text("status in ('pending','approved')"),
            sqlite_where=db.text("status in ('pending','approved')"),
        ),
    )

    def __repr__(self):
        return f"<WaReferralLink {self.id} company={self.company_id} {self.status}>"


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
