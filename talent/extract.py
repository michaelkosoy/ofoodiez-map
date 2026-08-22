"""CV text extraction + Gemini structured extraction for the Talent Inbox.

Cost discipline (§22-23): PDF/DOCX are parsed to TEXT locally (in the same
sandbox the CV reviewer uses — email attachments are untrusted) and only the
text goes to Gemini. The raw PDF is sent inline ONLY when local extraction
yields nothing (scanned PDFs). Output is a strict, small JSON schema — never
a rewritten CV.
"""
import base64
import json
import os
import re
import shutil
import tempfile
from datetime import datetime

from cv_review import sandbox
from cv_review.gemini import GeminiError, UsageTracker, api_key, generate_json
from database.models import db

from . import config
from .models import TalentAiLog

PDF_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pdf_worker.py')

_STR = {'type': 'string'}
_STR_ARR = {'type': 'array', 'items': _STR}

EXTRACTION_SCHEMA = {
    'type': 'object',
    'properties': {
        'name': _STR,
        'email': _STR,
        'phone': _STR,
        'city': _STR,
        'current_title': _STR,
        'seniority': {'type': 'string', 'enum': ['JUNIOR', 'MID', 'SENIOR', 'STAFF']},
        'years_experience': {'type': 'number'},
        'roles': _STR_ARR,
        'skills': _STR_ARR,
        'positions': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'title': _STR, 'company': _STR, 'period': _STR},
            'required': ['title'],
        }},
        'summary': _STR,
        'strengths': _STR_ARR,
        'concerns': _STR_ARR,
        'cv_quality': {'type': 'string', 'enum': ['GOOD', 'OK', 'POOR']},
        'rating': {'type': 'string', 'enum': ['STRONG', 'MAYBE', 'SKIP']},
        'rating_reasons': _STR_ARR,
    },
    'required': ['name', 'summary', 'skills', 'roles', 'cv_quality',
                 'rating', 'rating_reasons'],
}

EXTRACTION_PROMPT = """You triage CVs for a tech-referral service (Israeli hi-tech roles: engineering, product, data, security, DevOps).
Extract structured data from the CV below and rate how worth-referring the candidate is overall.

Rules:
- Output English only, even if the CV is in Hebrew.
- summary: 2-4 sentences, professional, factual.
- positions: the most relevant roles, newest first, max 4, period like "2023-Present".
- skills: real technologies/tools from the CV, max 20, canonical names (e.g. "Kubernetes" not "k8s").
- roles: 1-3 role labels this person fits (e.g. "Backend Engineer").
- years_experience: professional experience in years (estimate from dates; internships count half).
- strengths: max 5 short bullets, evidence-based.
- concerns: ONLY meaningful ones (max 4). If there are none, return an empty array — never invent filler concerns.
- rating: STRONG = clearly referrable, MAYBE = borderline/unclear, SKIP = not a fit for tech referrals.
- rating_reasons: 2-4 short bullets explaining the rating in plain language.
- Never include anything not evidenced in the CV.
"""


def _normalize(text):
    text = re.sub(r'[ \t]+', ' ', text or '')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()[:config.MAX_CV_TEXT_CHARS]


def _parse_pdf(file_bytes):
    """pypdf inside the one-shot sandbox (scrubbed env + rlimits + timeout)."""
    workdir = tempfile.mkdtemp(prefix='talentpdf-')
    in_path = os.path.join(workdir, 'input.pdf')
    out_path = os.path.join(workdir, 'verdict.json')
    try:
        with open(in_path, 'wb') as f:
            f.write(file_bytes)
        try:
            rc, _out, _err = sandbox.run_isolated_script(
                PDF_WORKER, [in_path, out_path], workdir=workdir)
        except Exception:
            return ''
        if rc != 0:
            return ''
        try:
            with open(out_path, encoding='utf-8') as f:
                verdict = json.load(f)
        except (OSError, ValueError):
            return ''
        return verdict.get('text', '') if verdict.get('ok') else ''
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def extract_text(file_bytes, ext):
    """Local text extraction. Returns (text, source) — text may be '' when the
    document has no extractable text (e.g. scanned PDF)."""
    if ext == '.docx':
        verdict = sandbox.parse_docx(file_bytes)
        if verdict.get('ok'):
            return _normalize(verdict.get('text', '')), 'docx'
        return '', 'none'
    if ext == '.pdf':
        return _normalize(_parse_pdf(file_bytes)), 'pypdf'
    return '', 'none'


def log_ai_call(kind, candidate_id, tracker, ok=True, error=None):
    """One TalentAiLog row per API call from the tracker's last entry (§26).
    Token counters only, never content."""
    last = tracker.calls[-1] if tracker.calls else {}
    db.session.add(TalentAiLog(
        kind=kind,
        model=last.get('model') or '',
        candidate_id=candidate_id,
        input_tokens=last.get('input_tokens', 0),
        cached_tokens=last.get('cached_tokens', 0),
        output_tokens=last.get('output_tokens', 0) + last.get('thoughts_tokens', 0),
        seconds=last.get('seconds'),
        ok=ok, error=(error or None) and str(error)[:500],
    ))
    db.session.commit()


def _call_with_fallback(parts, schema, *, purpose, tracker, model, kind,
                        candidate_id, max_output_tokens=2048):
    """One structured call on the configured cheap model; retry once on the
    explicit fallback model ONLY if one is configured (§21 — off by default)."""
    key = api_key()
    if not key:
        raise GeminiError('GEMINI_API_KEY is not configured')
    models = [model]
    fb = config.fallback_model()
    if fb and fb != model:
        models.append(fb)
    last_exc = None
    for m in models:
        try:
            data = generate_json(parts, schema, purpose=purpose, usage=tracker,
                                 key=key, model=m,
                                 max_output_tokens=max_output_tokens)
            log_ai_call(kind, candidate_id, tracker, ok=True)
            return data
        except GeminiError as exc:
            last_exc = exc
            log_ai_call(kind, candidate_id, tracker, ok=False, error=exc)
    raise last_exc


def run_extraction(cv, candidate):
    """Gemini structured extraction for one CV version. Stores the analysis on
    the CV row (§24: cached per version) and backfills EMPTY candidate fields
    only — admin edits are never clobbered by a re-run."""
    cv.analysis_status = 'running'
    db.session.commit()
    tracker = UsageTracker()
    try:
        if cv.text:
            parts = [{'text': EXTRACTION_PROMPT},
                     {'text': 'CV TEXT:\n' + cv.text}]
        elif cv.ext == '.pdf' and cv.file:
            # Scanned/imageless-text PDF — the one case the raw file goes up.
            parts = [{'text': EXTRACTION_PROMPT},
                     {'inline_data': {
                         'mime_type': 'application/pdf',
                         'data': base64.b64encode(cv.file).decode('ascii')}}]
        else:
            raise GeminiError('No readable text in this document')

        data = _call_with_fallback(
            parts, EXTRACTION_SCHEMA, purpose='talent_extract',
            tracker=tracker, model=config.extraction_model(),
            kind='extract', candidate_id=candidate.id)

        cv.analysis = data
        cv.analysis_status = 'complete'
        cv.analysis_error = None
        cv.analysis_model = tracker.calls[-1]['model'] if tracker.calls else config.extraction_model()
        cv.extraction_version = config.EXTRACTION_VERSION
        cv.analyzed_at = datetime.utcnow()

        def fill(field, value, cap=256):
            if value and not getattr(candidate, field):
                setattr(candidate, field, str(value)[:cap])
        fill('name', data.get('name'))
        fill('email', (data.get('email') or '').lower())
        fill('phone', data.get('phone'), 64)
        fill('city', data.get('city'), 128)
        fill('current_title', data.get('current_title'))
        if data.get('seniority') and not candidate.seniority:
            candidate.seniority = data['seniority']
        if data.get('years_experience') is not None and candidate.years_experience is None:
            try:
                candidate.years_experience = round(float(data['years_experience']), 1)
            except (TypeError, ValueError):
                pass
        db.session.commit()
        return data
    except GeminiError as exc:
        db.session.rollback()
        cv.analysis_status = 'failed'
        cv.analysis_error = str(exc)[:500]
        db.session.commit()
        raise
