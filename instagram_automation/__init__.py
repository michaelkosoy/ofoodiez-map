"""
Instagram DM Automation Service
A self-hosted ManyChat/LinkDM alternative.
"""

from flask import Blueprint

ig_bp = Blueprint(
    'instagram_automation',
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='static',
    url_prefix='/ig'
)

def init_app(app):
    """Register the Instagram automation blueprint with the Flask app."""
    from . import auth, webhooks, dashboard
    from database.models import db, init_db

    # Initialize database
    init_db(app)

    # Register blueprint
    app.register_blueprint(ig_bp)

    return app
