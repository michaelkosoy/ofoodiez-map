"""
Core Database Configuration and Models for the Website.
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import sqlalchemy as sa
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

def _run_migrations():
    """Add any columns that are missing from existing tables (safe to run repeatedly)."""
    migrations = [
        "ALTER TABLE hitech_emails ADD COLUMN IF NOT EXISTS linkedin_url TEXT",
        "ALTER TABLE hitech_emails ADD COLUMN IF NOT EXISTS job_title TEXT",
        "ALTER TABLE hitech_emails ADD COLUMN IF NOT EXISTS list_name TEXT",
        "ALTER TABLE site_users ADD COLUMN IF NOT EXISTS google_id VARCHAR(64)",
        "ALTER TABLE site_users ADD COLUMN IF NOT EXISTS payplus_sub_uid VARCHAR(64)",
        "ALTER TABLE site_users ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP",
        "ALTER TABLE site_users ALTER COLUMN password_hash DROP NOT NULL",
        "ALTER TABLE ig_happy_hours ADD COLUMN IF NOT EXISTS google_maps_link TEXT",
        "ALTER TABLE hitech_emails ADD COLUMN IF NOT EXISTS last_campaign TEXT",
        "ALTER TABLE hitech_emails ADD COLUMN IF NOT EXISTS last_sent_at TIMESTAMP",
        "ALTER TABLE hitech_emails ADD COLUMN IF NOT EXISTS company TEXT",
        "ALTER TABLE hitech_emails ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE",
        "ALTER TABLE hitech_emails ADD COLUMN IF NOT EXISTS gender TEXT",
        "ALTER TABLE hitech_emails ADD COLUMN IF NOT EXISTS name TEXT",
        # Plain ADD COLUMN (no IF NOT EXISTS) so these also run on local sqlite;
        # reruns fail with "duplicate column" and are swallowed below.
        "ALTER TABLE portfolio_access ADD COLUMN show_launch BOOLEAN DEFAULT TRUE",
        "ALTER TABLE portfolio_access ADD COLUMN show_boost BOOLEAN DEFAULT TRUE",
        "ALTER TABLE portfolio_access ADD COLUMN launch_price VARCHAR(64)",
        "ALTER TABLE portfolio_access ADD COLUMN launch_price_note VARCHAR(256)",
        "ALTER TABLE portfolio_access ADD COLUMN boost_price VARCHAR(64)",
        # 2026-07 pricing revamp: the old "Boost" package became "Presence" and a
        # new mid-tier "Boost" reuses the boost_* column names. Rename, then add
        # the new columns. Codes created before PORTFOLIO_REVAMP_CUTOFF are
        # served the frozen legacy pricing page (portfolio_pricing_legacy.html),
        # so already-sent offers change in nothing — no data rewrite needed.
        "ALTER TABLE portfolio_access RENAME COLUMN show_boost TO show_presence",
        "ALTER TABLE portfolio_access RENAME COLUMN boost_price TO presence_price",
        "ALTER TABLE portfolio_access ADD COLUMN show_pricing BOOLEAN DEFAULT TRUE",
        "ALTER TABLE portfolio_access ADD COLUMN show_boost BOOLEAN DEFAULT TRUE",
        "ALTER TABLE portfolio_access ADD COLUMN boost_price VARCHAR(64)",
    ]
    # Commit per statement: on Postgres a later failure's rollback would other-
    # wise wipe earlier uncommitted successes in the same transaction (sqlite
    # was immune — pysqlite implicitly commits before DDL), which silently
    # dropped new columns in prod.
    for stmt in migrations:
        try:
            db.session.execute(sa.text(stmt))
            db.session.commit()
        except Exception:
            db.session.rollback()


def _seed_listings():
    """First-run import of each listing page's curated entries from its
    blog_<slug>.json into listing_entries. A no-op once a page has rows, so it
    never overwrites what was edited in the admin panel."""
    try:
        from listing_submissions import LISTING_SUBMISSION_CONFIGS, seed_entries
        for slug in LISTING_SUBMISSION_CONFIGS:
            seed_entries(slug)
    except Exception as e:
        print(f"⚠️ listing seed skipped: {e}")


def init_db(app):
    """Initialize the database with the Flask app."""
    # Try to load IG_DATABASE_URL first for backward compatibility with existing envs,
    # then fallback to DATABASE_URL or SQLite.
    import os
    _db_url = os.environ.get('IG_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if _db_url:
        if _db_url.startswith('postgres://'):
            _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = app.config.get(
            'SQLALCHEMY_DATABASE_URI', 
            'sqlite:///instagram_automation.db'
        )
        
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _run_migrations()
        _seed_listings()


class PopupEvent(db.Model):
    """Calendar popup event added via Telegram bot."""
    __tablename__ = 'popup_events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    date = db.Column(db.String(256), nullable=False)  # "YYYY-MM-DD" or "YYYY-MM-DD | YYYY-MM-DD"
    time = db.Column(db.String(64))
    location = db.Column(db.String(256))
    location_link = db.Column(db.Text)
    description = db.Column(db.Text)
    instagram_username = db.Column(db.String(128))
    instagram_link = db.Column(db.Text)
    image = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "date": self.date,
            "time": self.time or "",
            "location": self.location or "",
            "location_link": self.location_link or "",
            "description": self.description or "",
            "instagram_username": self.instagram_username or "",
            "instagram_link": self.instagram_link or "",
            "image": self.image or ""
        }

    def __repr__(self):
        return f'<PopupEvent "{self.title}" on {self.date}>'


class HappyHourPlace(db.Model):
    """Happy Hour location data mapped from Google Sheets."""
    __tablename__ = 'ig_happy_hours'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False)
    name_hebrew = db.Column(db.String(256))
    address = db.Column(db.Text)
    city = db.Column(db.String(128))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    category = db.Column(db.String(128))
    description = db.Column(db.Text)
    opening_hours = db.Column(db.Text)
    
    # Days active (boolean)
    sunday = db.Column(db.Boolean, default=False)
    monday = db.Column(db.Boolean, default=False)
    tuesday = db.Column(db.Boolean, default=False)
    wednesday = db.Column(db.Boolean, default=False)
    thursday = db.Column(db.Boolean, default=False)
    friday = db.Column(db.Boolean, default=False)
    saturday = db.Column(db.Boolean, default=False)
    
    # Links & Metadata
    reservation_link = db.Column(db.Text)
    google_maps_link = db.Column(db.Text)
    instagram_url = db.Column(db.Text)
    image_url = db.Column(db.Text)
    verified = db.Column(db.Boolean, default=False)
    kosher = db.Column(db.Boolean, default=False)
    recommended = db.Column(db.Text) # Video link
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "Name": self.name,
            "NameHebrew": self.name_hebrew or "",
            "Address": self.address or "",
            "City": self.city or "",
            "Latitude": self.latitude,
            "Longitude": self.longitude,
            "Category": self.category or "",
            "Description": self.description or "",
            "OpeningHours": self.opening_hours or "",
            "Sunday": self.sunday,
            "Monday": self.monday,
            "Tuesday": self.tuesday,
            "Wednesday": self.wednesday,
            "Thursday": self.thursday,
            "Friday": self.friday,
            "Saturday": self.saturday,
            "ReservationLink": self.reservation_link or "",
            "GoogleMapsLink": self.google_maps_link or "",
            "InstagramURL": self.instagram_url or "",
            "ImageURL": self.image_url or "",
            "Verified": self.verified,
            "Kosher": self.kosher,
            "Recommended": self.recommended or ""
        }

    def __repr__(self):
        return f'<HappyHourPlace "{self.name}">'


class HitechEmail(db.Model):
    """Tech community member collected from the HiTech community page."""
    __tablename__ = 'hitech_emails'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(256), nullable=False, unique=True)
    name = db.Column(db.Text)
    linkedin_url = db.Column(db.Text)
    job_title = db.Column(db.Text)
    company = db.Column(db.Text)
    verified = db.Column(db.Boolean, default=False)
    gender = db.Column(db.String(16))
    list_name = db.Column(db.Text)       # admin-assigned email list tag (e.g. "founders", "cto")
    # Bulk-campaign bookkeeping: campaign identity = the email subject. Marked per
    # recipient right after a successful send, so a re-trigger with the SAME subject
    # resumes (skips those already sent) instead of duplicating — survives restarts
    # and email daily-quota cutoffs.
    last_campaign = db.Column(db.Text)
    last_sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<HitechEmail "{self.email}">'


class User(db.Model):
    """Site member account: registration/login + paid 'Services' access.

    Table auto-creates via init_db()'s db.create_all() at startup (this model is
    registered when database.models is imported, before init_db runs).
    """
    __tablename__ = 'site_users'  # explicit; avoids clashing with the bot's wa_users

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(256), nullable=False, unique=True)  # stored lowercased
    password_hash = db.Column(db.Text)                # null for Google-SSO-only accounts
    name = db.Column(db.String(128))
    google_id = db.Column(db.String(64), unique=True) # Google "sub"; set for SSO accounts
    is_paid = db.Column(db.Boolean, default=False)    # set True by the PayPlus callback on a successful charge
    paid_until = db.Column(db.DateTime)               # subscription period end (extended each recurring charge)
    payplus_sub_uid = db.Column(db.String(64))        # PayPlus recurring_uid, for reference/cancellation
    paid_at = db.Column(db.DateTime)                  # when the most recent payment landed (Grow one-time / audit)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_access(self):
        """True if the member may enter the gated Services area."""
        return bool(self.is_paid or (self.paid_until and self.paid_until > datetime.utcnow()))

    def __repr__(self):
        return f'<User {self.email}>'


class Purchase(db.Model):
    """A one-time Grow item purchase (per-item access: guides etc.).
    `item` is a slug registered in billing.GROW_ITEMS. Granted by the Grow webhook
    (cField2 / catalog-number match) or manually via the admin Members grid."""
    __tablename__ = 'site_purchases'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('site_users.id'), nullable=False, index=True)
    item = db.Column(db.String(64), nullable=False)
    paid_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'item', name='uq_purchase_user_item'),)


# Access codes created before this moment were sent an offer on the OLD
# pricing (Launch + old Boost) — they get the frozen legacy pricing page and
# must never see the revamped packages or prices (naive UTC, like created_at).
PORTFOLIO_REVAMP_CUTOFF = datetime(2026, 7, 27, 11, 0)


class PortfolioAccess(db.Model):
    """A per-company access code for the private /portfolio page.

    Created from the admin 'Portfolio Access' page when a proposal is sent;
    valid for 7 days (renewable). The code is stored in plain text on purpose:
    the admin has to read it back to send it to the client, and it's a
    low-value, short-lived, shared code — not a user credential.
    Table auto-creates via init_db()'s db.create_all() at startup."""
    __tablename__ = 'portfolio_access'

    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(128), nullable=False)
    code = db.Column(db.String(128), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    # Per-company pricing page: which packages this client sees and optional
    # price-text overrides (NULL → the page's standard price/copy).
    # 2026-07 revamp: the old "Boost" package is now "Presence" — its data was
    # migrated to show_presence/presence_price (see _run_migrations), and the
    # boost_* columns belong to the NEW mid-tier Boost package.
    show_launch = db.Column(db.Boolean, default=True)
    show_boost = db.Column(db.Boolean, default=True)
    show_presence = db.Column(db.Boolean, default=True)
    # Whole pricing page on/off for this code (NULL/True → visible).
    show_pricing = db.Column(db.Boolean, default=True)
    launch_price = db.Column(db.String(64))
    launch_price_note = db.Column(db.String(256))
    boost_price = db.Column(db.String(64))
    presence_price = db.Column(db.String(64))

    def is_active(self):
        return bool(self.expires_at and self.expires_at > datetime.utcnow())

    def is_legacy_pricing(self):
        """True for codes whose offer predates the 2026-07 pricing revamp —
        they see the frozen old pricing page, never the new packages."""
        return bool(self.created_at and self.created_at < PORTFOLIO_REVAMP_CUTOFF)

    def __repr__(self):
        return f'<PortfolioAccess {self.company} ({self.code})>'


class ListingEntry(db.Model):
    """One venue/supplier row of a listing page — bachelorette venues + suppliers,
    HiTech vendors; the per-page config lives in listing_submissions.py.

    These rows are in the DB rather than in app/data/blog_<slug>.json because both
    the public "add your business" form and the admin grid write them *in
    production*, and Render's filesystem is ephemeral: a file write there is erased
    by the next deploy or restart. The JSON file keeps only the static copy
    (intro/games/designs/gifts), which is edited in git.

    `data` is the entry exactly as the page template consumes it (name, category,
    description, price, links, contact_*, status, submitted_at), so a new form field
    needs no migration. Table auto-creates via init_db()'s db.create_all().

    ponytail: `status` stays inside `data` and is filtered in Python instead of
    being its own indexed column — it's a few dozen rows per page; promote it to a
    real column with a WHERE clause if a listing ever grows into the thousands.
    """
    __tablename__ = 'listing_entries'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), nullable=False, index=True)  # LISTING_SUBMISSION_CONFIGS key
    kind = db.Column(db.String(32), nullable=False)              # 'venue' / 'supplier'
    position = db.Column(db.Integer, default=0)                  # display order within a kind
    data = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ListingEntry {self.slug}/{self.kind} {(self.data or {}).get("name")}>'
