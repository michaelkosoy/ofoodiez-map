"""Job-input handling for the CV optimizer: pasted text only, NEVER job URLs.

The product deliberately does not fetch job-posting URLs — no LinkedIn/
Greenhouse/Lever/Workday scraping, no URL Context, no browser fetching, no
HTTP requests to user-provided links. Users paste the actual text. This keeps
the SSRF surface at zero and removes site-compatibility problems by design.
"""
import re

MAX_JOB_TITLE = 200
MAX_JOB_DESCRIPTION = 30_000
MAX_INSTRUCTIONS = 2_000

URL_REJECT_MESSAGE = 'Please paste the job description text instead of a job-posting link.'

# Tokens that clearly represent links. Two tiers:
#  - _URL_RE: schemes, www.*, known job boards, and bare domains WITH a path.
#    These are removed from otherwise-valid pasted JDs ("Learn more at ...")
#    and are never fetched.
#  - _BARE_DOMAIN_RE: a lone "company.com" style token — only used to classify
#    a submission that is nothing BUT a link. It is deliberately not used for
#    token removal so tech terms like "ASP.NET" or "socket.io" survive inside
#    real JD text.
_JOB_BOARDS = r'(?:linkedin\.com|greenhouse\.io|lever\.co|myworkdayjobs\.com|workday\.com|comeet\.com|indeed\.com|glassdoor\.com)'
_URL_RE = re.compile(
    r'(?i)\b(?:'
    r'https?://\S+'
    r'|www\.\S+'
    r'|\S*\b' + _JOB_BOARDS + r'\S*'
    r'|[a-z0-9][a-z0-9.-]*\.[a-z]{2,10}/\S+'   # bare domain with a path
    r')')
_BARE_DOMAIN_RE = re.compile(
    r'(?i)^[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:com|io|co|net|org|ai|jobs|careers|dev|il|us|uk)(?:/\S*)?$')

_CONTROL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


class JobInputError(ValueError):
    """User-facing job-input problem; str(exc) is safe to show the client."""


def _clean(text, limit, label):
    text = _CONTROL_RE.sub('', (text or '')).strip()
    if len(text) > limit:
        raise JobInputError(f'{label} is too long (max {limit:,} characters).')
    return text


def normalize_job_input(job_title, job_description, instructions):
    """Validate and normalize the three job-input fields.

    Returns {'job_title', 'job_description', 'instructions', 'removed_urls'}.
    Raises JobInputError with a user-facing message. Removed URLs are recorded
    for transparency and are NEVER fetched.
    """
    job_title = _clean(job_title, MAX_JOB_TITLE, 'Job title')
    job_description = _clean(job_description, MAX_JOB_DESCRIPTION, 'Job description')
    instructions = _clean(instructions, MAX_INSTRUCTIONS, 'Additional instructions')

    # A URL pasted as the "title" is the same mistake as a URL-only JD.
    if job_title and (_URL_RE.fullmatch(job_title) or _BARE_DOMAIN_RE.match(job_title)):
        raise JobInputError(URL_REJECT_MESSAGE)

    removed_urls = []
    if job_description:
        # URL-only submission (a single bare-domain token counts too).
        if _BARE_DOMAIN_RE.match(job_description):
            raise JobInputError(URL_REJECT_MESSAGE)
        removed_urls = [m.group(0) for m in _URL_RE.finditer(job_description)]
        remainder = _URL_RE.sub(' ', job_description)
        remainder_len = len(re.sub(r'\s+', ' ', remainder).strip())
        if removed_urls and remainder_len < 80:
            # Primarily a link, not a pasted description.
            raise JobInputError(URL_REJECT_MESSAGE)
        if removed_urls:
            job_description = re.sub(r'[ \t]{2,}', ' ', remainder).strip()

    # Instructions may also carry stray links — strip, never fetch.
    if instructions and _URL_RE.search(instructions):
        instructions = re.sub(r'[ \t]{2,}', ' ', _URL_RE.sub(' ', instructions)).strip()

    return {
        'job_title': job_title,
        'job_description': job_description,
        'instructions': instructions,
        'removed_urls': removed_urls,
    }
