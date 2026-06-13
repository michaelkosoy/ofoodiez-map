"""
Database models for the Instagram DM Automation Service.
Uses Flask-SQLAlchemy with SQLite (MVP) / PostgreSQL (production).
"""
from datetime import datetime, timedelta
from database.models import db


class User(db.Model):
    """A connected Instagram Professional account."""
    __tablename__ = 'ig_users'

    id = db.Column(db.Integer, primary_key=True)
    ig_user_id = db.Column(db.String(64), unique=True, nullable=False)
    ig_username = db.Column(db.String(128))
    access_token = db.Column(db.Text, nullable=False)  # Long-lived token
    token_expires_at = db.Column(db.DateTime)
    profile_picture_url = db.Column(db.Text)
    account_type = db.Column(db.String(32))  # BUSINESS or CREATOR
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    automations = db.relationship('Automation', backref='user', lazy=True)
    contacts = db.relationship('Contact', backref='user', lazy=True)

    def is_token_expired(self):
        if not self.token_expires_at:
            return True
        return datetime.utcnow() >= self.token_expires_at

    def token_days_remaining(self):
        if not self.token_expires_at:
            return 0
        delta = self.token_expires_at - datetime.utcnow()
        return max(0, delta.days)

    def __repr__(self):
        return f'<User @{self.ig_username}>'


class Contact(db.Model):
    """A person who interacted with the connected IG account."""
    __tablename__ = 'ig_contacts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('ig_users.id'), nullable=False)
    igsid = db.Column(db.String(64), nullable=False)  # Instagram-Scoped ID
    username = db.Column(db.String(128))
    email = db.Column(db.String(256))
    phone = db.Column(db.String(32))
    custom_fields = db.Column(db.JSON, default=dict)
    tags = db.Column(db.JSON, default=list)
    first_interaction = db.Column(db.DateTime, default=datetime.utcnow)
    last_interaction = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    conversations = db.relationship('Conversation', backref='contact', lazy=True)

    def __repr__(self):
        return f'<Contact @{self.username or self.igsid}>'


class Automation(db.Model):
    """An automation rule (trigger → actions)."""
    __tablename__ = 'ig_automations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('ig_users.id'), nullable=False)
    name = db.Column(db.String(256), nullable=False)
    trigger_type = db.Column(db.String(32), nullable=False)
    # Trigger types: 'comment_keyword', 'story_mention', 'story_reply', 'dm_keyword', 'ice_breaker'

    trigger_config = db.Column(db.JSON, default=dict)
    # For comment_keyword: {"keywords": ["LINK", "INFO"], "media_id": null, "match_all_posts": true}
    # For dm_keyword: {"keywords": ["HELP", "MENU"]}

    actions = db.Column(db.JSON, default=list)
    # Array of action steps:
    # [
    #   {"type": "send_private_reply", "text": "Hey! Check your DMs 👀"},
    #   {"type": "send_text", "text": "Here's the link you requested 🔗 https://..."},
    #   {"type": "send_button_template", "text": "Want more?", "buttons": [...]}
    # ]

    is_active = db.Column(db.Boolean, default=True)
    trigger_count = db.Column(db.Integer, default=0)  # How many times it fired
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Automation "{self.name}" ({self.trigger_type})>'


class Conversation(db.Model):
    """A DM conversation thread between the IG account and a contact."""
    __tablename__ = 'ig_conversations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('ig_users.id'), nullable=False)
    contact_id = db.Column(db.Integer, db.ForeignKey('ig_contacts.id'), nullable=False)
    last_message_at = db.Column(db.DateTime)
    window_expires_at = db.Column(db.DateTime)  # 24-hour messaging window
    status = db.Column(db.String(32), default='active')
    # Status: 'active', 'expired', 'human_takeover'

    # Relationships
    messages = db.relationship('MessageLog', backref='conversation', lazy=True,
                               order_by='MessageLog.sent_at')

    def is_window_open(self):
        if not self.window_expires_at:
            return False
        return datetime.utcnow() < self.window_expires_at

    def __repr__(self):
        return f'<Conversation #{self.id}>'


class MessageLog(db.Model):
    """Log of every message sent and received."""
    __tablename__ = 'ig_messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('ig_conversations.id'), nullable=False)
    direction = db.Column(db.String(16), nullable=False)  # 'incoming' or 'outgoing'
    message_type = db.Column(db.String(32), default='text')
    # Types: 'text', 'image', 'button_template', 'quick_reply', 'private_reply'
    content = db.Column(db.JSON)
    # Content structure depends on type:
    # text: {"text": "Hello!"}
    # image: {"url": "https://..."}
    # button_template: {"text": "...", "buttons": [...]}

    ig_message_id = db.Column(db.String(128))  # Meta's message ID
    automation_id = db.Column(db.Integer, db.ForeignKey('ig_automations.id'), nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Message {self.direction} ({self.message_type})>'



