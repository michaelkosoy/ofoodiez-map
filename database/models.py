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
        "ALTER TABLE site_users ALTER COLUMN password_hash DROP NOT NULL",
        "ALTER TABLE ig_happy_hours ADD COLUMN IF NOT EXISTS google_maps_link TEXT",
        "ALTER TABLE hitech_emails ADD COLUMN IF NOT EXISTS company TEXT",
        "ALTER TABLE hitech_emails ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE",
    ]
    for stmt in migrations:
        try:
            db.session.execute(sa.text(stmt))
        except Exception:
            db.session.rollback()
    db.session.commit()


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
    linkedin_url = db.Column(db.Text)
    job_title = db.Column(db.Text)
    company = db.Column(db.Text)
    verified = db.Column(db.Boolean, default=False)
    list_name = db.Column(db.Text)       # admin-assigned email list tag (e.g. "founders", "cto")
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
