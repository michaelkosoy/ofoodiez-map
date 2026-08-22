"""Talent Inbox / referral-CRM tables.

The dashboard + DB are the SOURCE OF TRUTH for candidate status, company fit,
referral status/history and notes; Gmail is only an ingestion source and an
outbound transport (spec §38). CV files live in the DB (LargeBinary) because
prod's filesystem is ephemeral — same rule as cv_reviews.

Tables auto-create via init_db()'s db.create_all(): this module is imported in
app.py BEFORE init_ig_automation() runs.
"""
import uuid
from datetime import datetime

from database.models import db


def _uuid():
    return str(uuid.uuid4())


# Candidate workflow statuses. NEW = not yet human-reviewed; STRONG/MAYBE/SKIP
# are the admin's review verdict (AI's own rating lives in the CV analysis and
# never sets these by itself); COMPLETED/ARCHIVED close a candidate out.
CANDIDATE_STATUSES = ('NEW', 'STRONG', 'MAYBE', 'SKIP', 'COMPLETED', 'ARCHIVED')

REFERRAL_METHODS = ('REFERRAL_LINK', 'MANUAL_UPLOAD', 'EMAIL')

# Referral lifecycle. NEEDS_ACTION = I still have to do something;
# WAITING = ball is with the candidate (link sent); SUBMITTED = the CV is with
# the company; COMPLETED/CANCELLED close it out.
REFERRAL_STATUSES = ('NEEDS_ACTION', 'WAITING', 'SUBMITTED', 'COMPLETED', 'CANCELLED')

FIT_LEVELS = ('STRONG', 'MAYBE', 'NO_MATCH')


class TalentCompany(db.Model):
    """A company I can refer candidates to, plus how referrals happen there
    and what kind of candidate they want (AI matching context)."""
    __tablename__ = 'talent_companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    referral_method = db.Column(db.String(32), nullable=False)  # REFERRAL_METHODS

    # REFERRAL_LINK method
    referral_url = db.Column(db.Text)
    candidate_email_subject = db.Column(db.Text)   # NULL -> default template
    candidate_email_template = db.Column(db.Text)  # NULL -> default template

    # MANUAL_UPLOAD method
    portal_url = db.Column(db.Text)
    portal_instructions = db.Column(db.Text)

    # EMAIL method — recipients ALWAYS come from here, never from AI (§14)
    email_to = db.Column(db.String(256))
    email_cc = db.Column(db.String(256))
    email_subject_template = db.Column(db.Text)    # NULL -> default template
    email_body_template = db.Column(db.Text)       # NULL -> default template

    # Target profile (§17) — everything optional
    target_roles = db.Column(db.JSON)      # ["Backend Engineer", ...]
    target_seniority = db.Column(db.JSON)  # ["JUNIOR","MID","SENIOR","STAFF"]; empty = Any
    required_skills = db.Column(db.JSON)
    preferred_skills = db.Column(db.JSON)
    min_years = db.Column(db.Float)        # minimum PROFESSIONAL experience, not age
    locations = db.Column(db.JSON)
    hiring_notes = db.Column(db.Text)      # free-form instructions fed to AI matching

    internal_notes = db.Column(db.Text)    # admin-only, never sent anywhere
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<TalentCompany {self.name} {self.referral_method}>'


class TalentCandidate(db.Model):
    """One person who sent (or was given) a CV. UUID primary key on purpose:
    ids appear in admin URLs and must not be guessable (PII behind them)."""
    __tablename__ = 'talent_candidates'

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    name = db.Column(db.String(256))
    email = db.Column(db.String(256), index=True)
    phone = db.Column(db.String(64))
    city = db.Column(db.String(128))
    current_title = db.Column(db.String(256))
    seniority = db.Column(db.String(32))          # JUNIOR|MID|SENIOR|STAFF
    years_experience = db.Column(db.Float)
    status = db.Column(db.String(32), default='NEW', index=True)  # CANDIDATE_STATUSES
    source = db.Column(db.String(64), default='EMAIL')  # EMAIL | MANUAL | WHATSAPP | LINKEDIN | ...
    notes = db.Column(db.Text)                    # private admin notes (§30) — never sent out
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<TalentCandidate {self.name!r} {self.status}>'


class TalentEmail(db.Model):
    """Ingested source email (metadata + snippet only, for 'Original Email').
    message_id is the dedup key across syncs."""
    __tablename__ = 'talent_emails'

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(512), unique=True)
    from_name = db.Column(db.String(256))
    from_email = db.Column(db.String(256), index=True)
    subject = db.Column(db.Text)
    snippet = db.Column(db.Text)
    received_at = db.Column(db.DateTime)
    candidate_id = db.Column(db.String(36), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TalentCv(db.Model):
    """One CV version. The file is stored here (DB = durable store) and is
    ONLY served through the admin-authed download route — no public URLs (§6).

    One AI analysis per CV version (§24): the structured extraction is cached
    on this row with model/version/timestamp and only re-runs on a new CV,
    an explicit Re-analyze, or an extraction-version bump."""
    __tablename__ = 'talent_cvs'

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    candidate_id = db.Column(db.String(36),
                             db.ForeignKey('talent_candidates.id'),
                             nullable=False, index=True)
    version = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)
    filename = db.Column(db.String(256))
    ext = db.Column(db.String(8))                 # .pdf | .docx
    file = db.Column(db.LargeBinary)
    text = db.Column(db.Text)                     # locally extracted text ('' if none)
    text_source = db.Column(db.String(16))        # pypdf | docx | none
    email_id = db.Column(db.Integer, index=True)  # talent_emails.id when from Gmail

    analysis = db.Column(db.JSON)                 # structured extraction (§22)
    analysis_status = db.Column(db.String(16), default='pending')  # pending|running|complete|failed
    analysis_error = db.Column(db.Text)
    analysis_model = db.Column(db.String(64))
    extraction_version = db.Column(db.Integer)
    analyzed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<TalentCv v{self.version} {self.filename} {self.analysis_status}>'


class TalentMatch(db.Model):
    """Candidate x company fit. AI writes ai_* fields; the admin override
    (admin_fit) is separate and ALWAYS wins in the UI — a future AI re-run
    never touches it (§9)."""
    __tablename__ = 'talent_matches'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.String(36), nullable=False, index=True)
    company_id = db.Column(db.Integer, nullable=False, index=True)
    ai_fit = db.Column(db.String(16))             # FIT_LEVELS; NULL for manual-only adds
    ai_pros = db.Column(db.JSON)                  # ["Backend engineer", ...] -> rendered as check marks
    ai_cons = db.Column(db.JSON)                  # ["Go not mentioned", ...] -> rendered as triangles
    admin_fit = db.Column(db.String(16))          # manual override, wins over ai_fit
    overridden = db.Column(db.Boolean, default=False)
    source = db.Column(db.String(16), default='AI')  # AI | MANUAL
    model = db.Column(db.String(64))
    matched_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('candidate_id', 'company_id',
                                          name='uq_talent_match'),)

    def effective_fit(self):
        return self.admin_fit or self.ai_fit


class TalentReferral(db.Model):
    """One referral of one candidate to one company. `method` is a SNAPSHOT of
    the company's referral method at creation time — editing the company later
    never rewrites history (§15)."""
    __tablename__ = 'talent_referrals'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.String(36), nullable=False, index=True)
    company_id = db.Column(db.Integer, nullable=False, index=True)
    cv_id = db.Column(db.String(36))              # CV version actually used
    method = db.Column(db.String(32))             # snapshot of REFERRAL_METHODS
    status = db.Column(db.String(32), default='NEEDS_ACTION', index=True)
    events = db.Column(db.JSON, default=list)     # [{'at': iso, 'event': str, 'detail': str}]
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def add_event(self, event, detail=''):
        # JSON columns don't track in-place mutation — reassign.
        self.events = (self.events or []) + [{
            'at': datetime.utcnow().isoformat(timespec='seconds'),
            'event': event, 'detail': detail}]


class TalentAiLog(db.Model):
    """One row per Gemini API call (§26): model, tokens, latency, outcome.
    Never any CV content. Feeds the AI-usage page (§27)."""
    __tablename__ = 'talent_ai_log'

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(16))               # extract | match
    model = db.Column(db.String(64))
    candidate_id = db.Column(db.String(36))
    input_tokens = db.Column(db.Integer, default=0)
    cached_tokens = db.Column(db.Integer, default=0)
    output_tokens = db.Column(db.Integer, default=0)
    seconds = db.Column(db.Float)
    ok = db.Column(db.Boolean, default=True)
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
