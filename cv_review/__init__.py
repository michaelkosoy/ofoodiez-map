"""AI CV reviewer + optimizer for the /hitech section (V2).

GET  /hitech/cv-review                 — upload page (password-gated beta)
POST /api/hitech/cv-review             — multipart: cv (.pdf/.docx/.txt ≤5MB),
                                         job_title, job_description (pasted
                                         TEXT only — job URLs are rejected,
                                         never fetched), instructions,
                                         talent_pool_consent.
POST /api/hitech/cv-review/confirm-name — continue a review that paused for
                                         candidate-name confirmation.
GET  /hitech/cv-review/download/<id>/<kind> — docx | pdf | txt (session-owned
                                         or admin).

Registered in app.py with:
    from cv_review import cv_review_bp
    app.register_blueprint(cv_review_bp)
"""
import os
import time
from urllib.parse import quote

from flask import (Blueprint, Response, current_app, jsonify, redirect,
                   render_template, request, session, url_for)

from . import gemini, pipeline, storage
from .jobspec import JobInputError, normalize_job_input
from .pipeline import PipelineError

cv_review_bp = Blueprint('cv_review', __name__)

MAX_CV_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = ('.pdf', '.docx', '.txt')   # .docm/.dotm etc. rejected

# ── Per-IP rate limit ────────────────────────────────────────────────────────
# ponytail: in-memory dict — correct for the single gunicorn worker in the
# Procfile; move to flask-limiter/redis if --workers ever grows past 1.
RATE_LIMIT = 5        # reviews…
RATE_WINDOW = 3600    # …per hour, per client IP (name-confirmation resumes
                      # and downloads are not counted)
_recent_reviews = {}  # ip -> [timestamps]


def _client_ip():
    return (request.headers.get('CF-Connecting-IP')
            or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or request.remote_addr or 'unknown')


def _rate_limited(ip):
    now = time.time()
    hits = [t for t in _recent_reviews.get(ip, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_LIMIT:
        _recent_reviews[ip] = hits
        return True
    hits.append(now)
    _recent_reviews[ip] = hits
    if len(_recent_reviews) > 10000:  # ponytail: crude memory guard
        _recent_reviews.clear()
    return False


# Now that the reviewer is public, every run spends real Gemini money
# (~$0.03) with no login behind it. The per-IP limit above doesn't bound the
# total, so a whole-site daily cap is the budget backstop. Raise/lower with
# CV_REVIEW_DAILY_CAP (0 = unlimited).
DAILY_CAP_DEFAULT = 200


def _daily_cap_reached():
    cap = int(os.environ.get('CV_REVIEW_DAILY_CAP', DAILY_CAP_DEFAULT))
    if cap <= 0:
        return False
    from datetime import datetime, timedelta

    from database.models import CvReview
    since = datetime.utcnow() - timedelta(hours=24)
    try:
        used = CvReview.query.filter(CvReview.created_at >= since).count()
    except Exception as exc:            # never block a review on a count query
        print(f'⚠️ CV review: daily-cap check failed ({exc})')
        return False
    if used >= cap:
        print(f'⚠️ CV review: daily cap reached ({used}/{cap})')
        return True
    return False


def _review_unlocked():
    """The reviewer is OPEN TO EVERYONE (public launch 2026-08-18).

    ponytail: the shared-password gate below is kept but bypassed — set
    CV_REVIEW_PASSWORD_ENABLED=1 to re-close it (same pattern as
    /hitech/cv-guide/full). Consent to store the CV is still required.
    """
    if os.environ.get('CV_REVIEW_PASSWORD_ENABLED') != '1':
        return True
    return bool(session.get('cv_review_unlocked'))


def _remember_review(review_id):
    ids = list(session.get('cv_review_ids') or [])
    ids.append(review_id)
    session['cv_review_ids'] = ids[-20:]


def _owns_review(review_id):
    return (session.get('admin_logged_in')
            or review_id in (session.get('cv_review_ids') or []))


@cv_review_bp.route('/hitech/cv-review', methods=['GET', 'POST'])
def cv_review_page():
    """The 'Review my CV with AI' page.

    ponytail: shared password gate (CV_REVIEW_PASSWORD, default 123456) until
    public launch — visitors see a Coming soon card with an unlock field.
    """
    error = False
    if request.method == 'POST':
        if request.form.get('password', '').strip() == os.environ.get('CV_REVIEW_PASSWORD', '123456'):
            session['cv_review_unlocked'] = True
            return redirect(url_for('cv_review.cv_review_page'))
        error = True
    return render_template('hitech_cv_review.html',
                           active_hitech_page='cv-review', active_page='hitech',
                           locked=not _review_unlocked(), error=error)


# The review runs in a background thread and the client POLLS — a long
# pipeline must never sit inside one HTTP request (Cloudflare caps origin
# responses at ~100s and swallows 502/504 bodies, which is exactly how the
# user ends up with a generic error and no explanation).
@cv_review_bp.route('/api/hitech/cv-review', methods=['POST'])
def cv_review_api():
    if not _review_unlocked():
        return jsonify({'error': 'The AI reviewer is not open yet — coming soon.'}), 403

    # Consent is REQUIRED: we keep the CV to run the review and for matching.
    if request.form.get('talent_pool_consent') != '1':
        return jsonify({'error': 'Please agree to the CV storage terms first — the review '
                                 'can\'t run without it. See "what we store and why" next '
                                 'to the checkbox.'}), 400

    file = request.files.get('cv')
    if file is None or not file.filename:
        return jsonify({'error': 'No CV file received. Please attach a .pdf, .docx or .txt file.'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': 'Unsupported file type. Please upload a .pdf, .docx or .txt file.'}), 400
    file_bytes = file.read()
    if len(file_bytes) > MAX_CV_BYTES:
        return jsonify({'error': 'This file is over 5 MB. Please upload a smaller one.'}), 413
    if not file_bytes:
        return jsonify({'error': 'The uploaded file is empty.'}), 400

    try:
        job = normalize_job_input(request.form.get('job_title'),
                                  request.form.get('job_description'),
                                  request.form.get('instructions'))
    except JobInputError as exc:
        return jsonify({'error': str(exc)}), 400

    if _rate_limited(_client_ip()):
        return jsonify({'error': f'Rate limit reached — up to {RATE_LIMIT} reviews per hour. '
                                 'Take the time to apply the fixes, then come back :)'}), 429

    if _daily_cap_reached():
        return jsonify({'error': 'The AI reviewer has hit its daily limit. '
                                 'Please come back tomorrow — it resets every day.'}), 429

    key = gemini.api_key()
    if key is None:
        return jsonify({'error': 'The AI reviewer is not configured on this server yet. '
                                 'Please try again later.'}), 503

    try:
        # File parsing/validation stays synchronous (fast) so hostile or
        # broken files are an immediate 400 — the model work goes async.
        doc_part = pipeline.file_to_evidence_parts(file_bytes, ext)
        review = pipeline.launch_review(
            current_app._get_current_object(), doc_part=doc_part,
            file_bytes=file_bytes, filename=file.filename, ext=ext, job=job,
            consent=True, owner_user_id=session.get('user_id'), key=key)
    except PipelineError as exc:
        return jsonify({'error': exc.user_message}), exc.status
    _remember_review(review.id)
    return jsonify({'status': 'processing', 'review_id': review.id})


@cv_review_bp.route('/api/hitech/cv-review/<review_id>/status')
def cv_review_status(review_id):
    if not _owns_review(review_id):
        return jsonify({'error': 'Review not found.'}), 404
    from database.models import CvReview
    review = CvReview.query.get(review_id)
    if review is None:
        return jsonify({'error': 'Review not found.'}), 404
    if review.status == 'processing':
        # A restart/deploy can kill the worker thread mid-review; don't let the
        # client poll a dead row for ten minutes.
        if storage.is_stale(review):
            storage.fail_stale_processing()
            return jsonify({'status': 'failed', 'review_id': review.id,
                            'error': storage.STALE_MESSAGE})
        return jsonify({'status': 'processing', 'review_id': review.id})
    if review.status == 'pending_name':
        return jsonify(review.result or {'status': 'needs_name_confirmation',
                                         'review_id': review.id, 'guessed_name': '',
                                         'message': ''})
    if review.status == 'failed':
        return jsonify({'status': 'failed', 'review_id': review.id,
                        'error': review.error or 'Something went wrong while reviewing '
                                                 'your CV. Please try again.'})
    payload = dict(review.result or {})
    payload.setdefault('status', 'complete')
    payload['optimized_text'] = review.optimized_text or ''
    return jsonify(payload)


@cv_review_bp.route('/api/hitech/cv-review/confirm-name', methods=['POST'])
def cv_review_confirm_name():
    if not _review_unlocked():
        return jsonify({'error': 'The AI reviewer is not open yet — coming soon.'}), 403
    data = request.get_json(silent=True) or {}
    review_id = str(data.get('review_id') or '')
    if not review_id or not _owns_review(review_id):
        return jsonify({'error': 'Review not found.'}), 404
    from database.models import CvReview
    review = CvReview.query.get(review_id)
    if review is None or review.status != 'pending_name':
        return jsonify({'error': 'Review not found.'}), 404
    key = gemini.api_key()
    if key is None:
        return jsonify({'error': 'The AI reviewer is not configured on this server yet.'}), 503
    try:
        pipeline.launch_resume(current_app._get_current_object(), review,
                               data.get('name'), key=key)
    except PipelineError as exc:
        return jsonify({'error': exc.user_message}), exc.status
    return jsonify({'status': 'processing', 'review_id': review.id})


@cv_review_bp.route('/hitech/cv-review/terms')
def cv_review_terms():
    """What we store and why — linked from the required consent checkbox."""
    return render_template('legal/cv_review_terms.html')


_KIND_MIME = {
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pdf': 'application/pdf',
    'txt': 'text/plain; charset=utf-8',
}


def serve_review_file(review, kind, allow_original=False):
    """Shared download response builder (public + admin routes).
    The RAW/UNTRUSTED original is only reachable when explicitly allowed
    (admin route with the explicit 'original_untrusted' kind)."""
    filenames = storage.review_filenames(review.candidate_name)
    if kind == 'original_untrusted' and allow_original:
        data = review.original_file
        filename = f"{filenames['original']}{review.original_ext or ''}"
        mime = 'application/octet-stream'
    elif kind in _KIND_MIME:
        data = {'docx': review.optimized_docx, 'pdf': review.optimized_pdf,
                'txt': (review.optimized_text or '').encode('utf-8')}[kind]
        filename = filenames[kind]
        mime = _KIND_MIME[kind]
    else:
        return jsonify({'error': 'Unknown file kind.'}), 404
    if not data:
        return jsonify({'error': 'File not available.'}), 404
    ascii_fallback = f'CV_Optimized.{kind if kind in _KIND_MIME else "bin"}'
    disposition = (f"attachment; filename=\"{ascii_fallback}\"; "
                   f"filename*=UTF-8''{quote(filename)}")
    return Response(data, mimetype=mime,
                    headers={'Content-Disposition': disposition,
                             'X-Content-Type-Options': 'nosniff'})


@cv_review_bp.route('/hitech/cv-review/download/<review_id>/<kind>')
def cv_review_download(review_id, kind):
    if not _owns_review(review_id):
        return jsonify({'error': 'Not found.'}), 404
    from database.models import CvReview
    review = CvReview.query.get(review_id)
    if review is None or review.status != 'complete':
        return jsonify({'error': 'Not found.'}), 404
    return serve_review_file(review, kind, allow_original=False)
