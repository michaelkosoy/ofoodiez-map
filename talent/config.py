"""Central Talent Inbox configuration — the ONE place model names live (§20).

Cost rules (§20-21): CV extraction and company matching both default to the
cheap gemini-3.5-flash-lite. A stronger model is used only if explicitly set
via env. The fallback model is DISABLED by default for predictable costs.
"""
import os

DEFAULT_TALENT_MODEL = 'gemini-3.5-flash-lite'

# Bump when the extraction prompt/schema changes enough that old analyses are
# stale; the UI offers Re-analyze, nothing re-runs automatically.
EXTRACTION_VERSION = 1


def extraction_model():
    return os.environ.get('GEMINI_CV_EXTRACTION_MODEL', DEFAULT_TALENT_MODEL)


def matching_model():
    return os.environ.get('GEMINI_CV_MATCHING_MODEL', DEFAULT_TALENT_MODEL)


def fallback_model():
    """Second-try model when the primary call fails outright. Empty = disabled
    (the default — §21 wants predictable costs)."""
    return os.environ.get('GEMINI_CV_FALLBACK_MODEL', '').strip() or None


def gmail_config():
    """Gmail ingestion via IMAP app password. Unset = sync disabled (the rest
    of the dashboard, incl. manual uploads, works without it)."""
    return {
        'user': os.environ.get('TALENT_GMAIL_USER', '').strip(),
        'password': os.environ.get('TALENT_GMAIL_APP_PASSWORD', '').strip(),
        'folder': os.environ.get('TALENT_GMAIL_FOLDER', 'INBOX'),
        'days': int(os.environ.get('TALENT_SYNC_DAYS', '30') or 30),
    }


MAX_CV_BYTES = 10 * 1024 * 1024
MAX_CV_TEXT_CHARS = 30000
ALLOWED_EXTS = ('.pdf', '.docx')

# ---- Outbound email templates (defaults; per-company overrides in DB) ------
# Safe {variable} substitution only — never executable template code (§12).

CANDIDATE_EMAIL_VARS = ('first_name', 'full_name', 'company_name', 'referral_url')
DEFAULT_CANDIDATE_EMAIL_SUBJECT = 'Your referral link for {company_name}'
DEFAULT_CANDIDATE_EMAIL_TEMPLATE = (
    'Hi {first_name},\n\n'
    'Thanks for sending your CV.\n\n'
    'You can apply to {company_name} through my referral link here:\n\n'
    '{referral_url}\n\n'
    'Good luck!'
)

REFERRAL_EMAIL_VARS = ('candidate_name', 'candidate_role', 'years_experience',
                       'candidate_highlights', 'company_name')
DEFAULT_REFERRAL_SUBJECT = 'Referral — {candidate_name} — {candidate_role}'
DEFAULT_REFERRAL_BODY = (
    'Hi,\n\n'
    'Sharing {candidate_name}, a {candidate_role} with approximately '
    '{years_experience} years of experience.\n\n'
    'Highlights:\n{candidate_highlights}\n\n'
    'CV attached.\n\n'
    'Thanks,\nOfir'
)
