"""
Configuration for Instagram DM Automation Service.
All secrets come from environment variables.
"""
import os

class Config:
    # Meta App credentials (from developers.facebook.com)
    META_APP_ID = os.environ.get('META_APP_ID', '')
    META_APP_SECRET = os.environ.get('META_APP_SECRET', '')
    
    # Webhook verification token (you define this, must match Meta dashboard)
    WEBHOOK_VERIFY_TOKEN = os.environ.get('WEBHOOK_VERIFY_TOKEN', 'ofoodiez_ig_verify_2025')
    
    # OAuth callback URL
    BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')
    
    @classmethod
    def get_oauth_redirect_uri(cls):
        """Get the OAuth redirect URI, dynamically matching host if BASE_URL is not set."""
        # If BASE_URL is explicitly set to something other than default localhost, use it
        env_base_url = os.environ.get('BASE_URL')
        if env_base_url:
            return f"{env_base_url}/ig/auth/callback"
        
        # Otherwise, check if we're in a Flask request context to dynamically construct it
        try:
            from flask import request
            if request:
                scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
                # Ensure we always use https for production
                if 'ofoodiez.com' in request.host:
                    scheme = 'https'
                return f"{scheme}://{request.host}/ig/auth/callback"
        except Exception:
            pass
            
        # Default fallback
        return f"{cls.BASE_URL}/ig/auth/callback"
    
    # Instagram OAuth URLs
    IG_AUTH_URL = "https://www.instagram.com/oauth/authorize"
    IG_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
    IG_GRAPH_URL = "https://graph.instagram.com"
    
    # Graph API version
    GRAPH_API_VERSION = "v25.0"
    
    # Scopes we request
    IG_SCOPES = "instagram_business_basic,instagram_business_manage_messages,instagram_manage_comments"
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('IG_DATABASE_URL', 'sqlite:///instagram_automation.db')
    
    # Security
    SECRET_KEY = os.environ.get('IG_SECRET_KEY', 'change-me-in-production-ig-auto')
    ENCRYPTION_KEY = os.environ.get('IG_ENCRYPTION_KEY', '')  # Fernet key for token encryption
    
    @classmethod
    def get_auth_url(cls):
        """Build the Instagram OAuth authorization URL."""
        return (
            f"{cls.IG_AUTH_URL}"
            f"?client_id={cls.META_APP_ID}"
            f"&redirect_uri={cls.get_oauth_redirect_uri()}"
            f"&response_type=code"
            f"&scope={cls.IG_SCOPES}"
        )
    
    @classmethod
    def validate(cls):
        """Check that required config is set."""
        missing = []
        if not cls.META_APP_ID:
            missing.append('META_APP_ID')
        if not cls.META_APP_SECRET:
            missing.append('META_APP_SECRET')
        return missing
