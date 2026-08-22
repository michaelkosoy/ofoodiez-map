"""Talent Inbox orchestration: create candidates/CV versions, run the
extraction + matching pipeline, and the background batch analyzer.

Every entry path (Gmail sync, manual add, CV replacement) funnels through
add_cv() -> analyze_candidate(), so all CVs get the exact same treatment (§35).
"""
import io
import logging
import os
import threading

from database.models import db

from . import config
from .extract import extract_text, run_extraction
from .matching import run_matching
from .models import TalentCandidate, TalentCompany, TalentCv

logger = logging.getLogger('talent')


def mirror_cv_to_drive(candidate, cv):
    """Best-effort personal copy of every incoming CV in Google Drive:
    <root>/Talent CVs/<Candidate_Name>/v<n>_<filename>. Reuses the CV
    reviewer's service-account setup (GOOGLE_DRIVE_CREDENTIALS_JSON); root is
    TALENT_DRIVE_FOLDER_ID, falling back to GOOGLE_DRIVE_CV_FOLDER_ID. Never
    fatal and never shared publicly — Postgres stays the durable store."""
    try:
        from cv_review import storage
        svc, root = storage._drive()
        if svc is None:
            return
        root = os.environ.get('TALENT_DRIVE_FOLDER_ID') or root
        from googleapiclient.http import MediaIoBaseUpload
        label = storage.sanitize_name(candidate.name or candidate.email
                                      or candidate.id)
        folder = storage._ensure_folder(svc, 'Talent CVs', root)
        cand_folder = storage._ensure_folder(svc, label, folder)
        mime = ('application/pdf' if cv.ext == '.pdf' else
                'application/vnd.openxmlformats-officedocument'
                '.wordprocessingml.document')
        stem = os.path.splitext(cv.filename or 'cv')[0]
        name = f'v{cv.version}_{storage.sanitize_name(stem)}{cv.ext}'
        media = MediaIoBaseUpload(io.BytesIO(cv.file), mimetype=mime,
                                  resumable=False)
        svc.files().create(body={'name': name, 'parents': [cand_folder]},
                           media_body=media, fields='id',
                           supportsAllDrives=True).execute()
        logger.info('talent: CV %s mirrored to Drive as %s', cv.id, name)
    except Exception as exc:
        logger.warning('talent: Drive mirror skipped (%s: %s)',
                       type(exc).__name__, exc)


class UploadError(ValueError):
    """User-facing upload validation problem."""


def validate_upload(file_bytes, filename):
    """Trust-boundary checks for any CV file entering the system."""
    ext = os.path.splitext(filename or '')[1].lower()
    if ext not in config.ALLOWED_EXTS:
        raise UploadError('Only PDF or DOCX files are supported.')
    if not file_bytes:
        raise UploadError('The file is empty.')
    if len(file_bytes) > config.MAX_CV_BYTES:
        raise UploadError('File too large (max 10MB).')
    if ext == '.pdf' and not file_bytes.startswith(b'%PDF-'):
        raise UploadError('This file is not a valid PDF.')
    if ext == '.docx' and not file_bytes.startswith(b'PK'):
        raise UploadError('This file is not a valid DOCX.')
    return ext


def ensure_candidate(email=None, name=None, source='EMAIL'):
    """Find by email (case-insensitive) or create. A repeat sender becomes a
    new CV VERSION on their existing card, never a duplicate person.
    Returns (candidate, created)."""
    email = (email or '').strip().lower()[:256] or None
    cand = None
    if email:
        cand = TalentCandidate.query.filter(
            db.func.lower(TalentCandidate.email) == email).first()
    if cand is not None:
        return cand, False
    cand = TalentCandidate(email=email, name=(name or '').strip()[:256] or None,
                           source=source)
    db.session.add(cand)
    db.session.flush()
    return cand, True


def add_cv(candidate, file_bytes, filename, email_id=None):
    """Store a new CV version (old versions kept, newest active — §36) and
    extract its text locally. No AI here — analysis is a separate step."""
    ext = validate_upload(file_bytes, filename)
    text, text_source = extract_text(file_bytes, ext)
    version = 1 + db.session.query(db.func.count(TalentCv.id)).filter(
        TalentCv.candidate_id == candidate.id).scalar()
    TalentCv.query.filter_by(candidate_id=candidate.id, is_active=True) \
        .update({'is_active': False})
    cv = TalentCv(candidate_id=candidate.id, version=version, is_active=True,
                  filename=(filename or f'cv-v{version}{ext}')[:256], ext=ext,
                  file=file_bytes, text=text, text_source=text_source,
                  email_id=email_id, analysis_status='pending')
    db.session.add(cv)
    db.session.commit()
    mirror_cv_to_drive(candidate, cv)  # personal copy, best-effort
    return cv


def analyze_candidate(candidate, cv=None):
    """Extraction + company matching for the candidate's active CV.
    Raises GeminiError on AI failure (already recorded on the CV row)."""
    cv = cv or TalentCv.query.filter_by(candidate_id=candidate.id,
                                        is_active=True).first()
    if cv is None:
        return None
    analysis = run_extraction(cv, candidate)
    companies = TalentCompany.query.filter_by(active=True).all()
    run_matching(candidate, analysis, companies)
    return analysis


# ---- Background batch analyzer ---------------------------------------------
# One at a time per process; a second sync while one runs just queues nothing
# extra — pending CVs are picked up by the running batch's next loop anyway.
_analyze_lock = threading.Lock()


def analyze_pending_async(app):
    """Analyze every pending CV in a background thread (same app-context
    pattern as cv_review). Fire-and-forget; per-CV failures are stored on the
    CV row and surfaced in the UI, never raised."""
    def worker():
        with app.app_context():
            if not _analyze_lock.acquire(blocking=False):
                return
            try:
                while True:
                    cv = TalentCv.query.filter_by(analysis_status='pending',
                                                  is_active=True) \
                        .order_by(TalentCv.created_at).first()
                    if cv is None:
                        break
                    cand = db.session.get(TalentCandidate, cv.candidate_id)
                    try:
                        analyze_candidate(cand, cv)
                    except Exception as exc:
                        logger.warning('talent analyze failed for %s: %s', cv.id, exc)
                        db.session.rollback()
                        # Extraction done but matching failed -> keep 'complete';
                        # otherwise mark failed so the row can't strand as
                        # pending/running and the UI offers Re-analyze.
                        if cv.analysis_status != 'complete':
                            cv.analysis_status = 'failed'
                            cv.analysis_error = str(exc)[:500]
                        db.session.commit()
            finally:
                _analyze_lock.release()

    threading.Thread(target=worker, daemon=True).start()
