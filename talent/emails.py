"""Outbound referral emails (Brevo) + safe template rendering.

Control rules (§8, §12, §14): nothing here is called automatically — only an
explicit admin action after a preview. Recipients ALWAYS come from stored data
(company config / candidate record), never from AI output. Templates support a
whitelist of {variables}; anything else is left verbatim — no template code.
"""
import base64
import html as html_mod
import logging
import os
import re

import requests

from . import config

logger = logging.getLogger('talent')

_BREVO_URL = 'https://api.brevo.com/v3/smtp/email'
_VAR_RE = re.compile(r'\{([a-z_]+)\}')


def render_vars(template, mapping, allowed):
    """Replace whitelisted {vars}; unknown/missing vars stay as-is."""
    def sub(match):
        key = match.group(1)
        if key in allowed and mapping.get(key) not in (None, ''):
            return str(mapping[key])
        return match.group(0)
    return _VAR_RE.sub(sub, template or '')


def _first_name(name):
    return (name or '').strip().split(' ')[0] or 'there'


def _fmt_years(years):
    if years is None:
        return ''
    return f'{years:g}'


def candidate_link_email(candidate, company):
    """Preview for the REFERRAL_LINK email sent TO THE CANDIDATE."""
    mapping = {
        'first_name': _first_name(candidate.name),
        'full_name': candidate.name or 'there',
        'company_name': company.name,
        'referral_url': company.referral_url or '',
    }
    allowed = set(config.CANDIDATE_EMAIL_VARS)
    subject = render_vars(company.candidate_email_subject
                          or config.DEFAULT_CANDIDATE_EMAIL_SUBJECT, mapping, allowed)
    body = render_vars(company.candidate_email_template
                       or config.DEFAULT_CANDIDATE_EMAIL_TEMPLATE, mapping, allowed)
    warnings = []
    if not candidate.email:
        warnings.append('Candidate has no email address on file.')
    if not company.referral_url:
        warnings.append('Company has no referral URL configured.')
    return {'to': candidate.email or '', 'cc': '', 'subject': subject,
            'body': body, 'warnings': warnings, 'attach_cv': False}


def company_referral_email(candidate, company, analysis):
    """Preview for the EMAIL-method referral sent TO THE COMPANY (CV attached).
    candidate_highlights come from the stored AI strengths — no new AI call."""
    a = analysis or {}
    highlights = '\n'.join(f'- {s}' for s in (a.get('strengths') or [])[:5]) \
        or '- (no AI highlights available)'
    role = a.get('current_title') or candidate.current_title \
        or (a.get('roles') or [None])[0] or 'candidate'
    mapping = {
        'candidate_name': candidate.name or 'the candidate',
        'candidate_role': role,
        'years_experience': _fmt_years(
            a.get('years_experience', candidate.years_experience)),
        'candidate_highlights': highlights,
        'company_name': company.name,
    }
    allowed = set(config.REFERRAL_EMAIL_VARS)
    subject = render_vars(company.email_subject_template
                          or config.DEFAULT_REFERRAL_SUBJECT, mapping, allowed)
    body = render_vars(company.email_body_template
                       or config.DEFAULT_REFERRAL_BODY, mapping, allowed)
    warnings = []
    if not company.email_to:
        warnings.append('Company has no referral recipient email configured.')
    return {'to': company.email_to or '', 'cc': company.email_cc or '',
            'subject': subject, 'body': body, 'warnings': warnings,
            'attach_cv': True}


def send_email(to, subject, text_body, cc=None, attachment=None):
    """Plain-text send via Brevo (same transport/env as the rest of the site:
    BREVO_API_KEY + WA_FROM_EMAIL). attachment = (filename, bytes) or None.
    Returns (ok, error_message)."""
    api_key = os.environ.get('BREVO_API_KEY')
    from_email = os.environ.get('WA_FROM_EMAIL')
    if not api_key or not from_email:
        return False, 'Email transport not configured (BREVO_API_KEY / WA_FROM_EMAIL).'
    if not to:
        return False, 'No recipient address.'
    body = {
        'sender': {'email': from_email, 'name': 'Michael — Ofoodiez'},
        'to': [{'email': to}],
        'subject': subject or '(no subject)',
        'textContent': text_body or '',
        # A minimal HTML part so clients render line breaks consistently.
        'htmlContent': ('<div style="font-family:Arial,Helvetica,sans-serif;'
                        'font-size:15px;color:#222;line-height:1.55;'
                        'white-space:pre-wrap;">'
                        f'{html_mod.escape(text_body or "")}</div>'),
        'replyTo': {'email': os.environ.get('WA_OPS_EMAIL', from_email)},
    }
    cc_list = [{'email': addr.strip()} for addr in (cc or '').split(',') if addr.strip()]
    if cc_list:
        body['cc'] = cc_list
    if attachment:
        filename, file_bytes = attachment
        body['attachment'] = [{'name': filename or 'cv.pdf',
                               'content': base64.b64encode(file_bytes).decode('ascii')}]
    try:
        resp = requests.post(_BREVO_URL, json=body, timeout=20,
                             headers={'api-key': api_key,
                                      'Content-Type': 'application/json'})
        if resp.status_code in (200, 201, 202):
            return True, None
        logger.warning('talent Brevo send failed: %s %s',
                       resp.status_code, resp.text[:200])
        return False, f'Email provider error ({resp.status_code}).'
    except requests.RequestException as exc:
        logger.exception('talent: Brevo send error')
        return False, f'Email send failed: {type(exc).__name__}.'
