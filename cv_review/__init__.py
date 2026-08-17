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

from flask import (Blueprint, Response, jsonify, redirect, render_template,
                   request, session, url_for)

from . import gemini, storage
from .jobspec import JobInputError, normalize_job_input
from .pipeline import PipelineError, resume_review, start_review

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


def _review_unlocked():
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


# NOTE: never return 502/504 from these APIs — Cloudflare replaces those
# bodies with its own error page and the frontend loses our JSON message.
@cv_review_bp.route('/api/hitech/cv-review', methods=['POST'])
def cv_review_api():
    if not _review_unlocked():
        return jsonify({'error': 'The AI reviewer is not open yet — coming soon.'}), 403

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

    key = gemini.api_key()
    if key is None:
        return jsonify({'error': 'The AI reviewer is not configured on this server yet. '
                                 'Please try again later.'}), 503

    try:
        payload, review = start_review(
            file_bytes=file_bytes, filename=file.filename, ext=ext, job=job,
            consent=request.form.get('talent_pool_consent') == '1',
            owner_user_id=session.get('user_id'), key=key)
    except PipelineError as exc:
        return jsonify({'error': exc.user_message}), exc.status
    _remember_review(review.id)
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
        payload = resume_review(review, data.get('name'), key=key)
    except PipelineError as exc:
        return jsonify({'error': exc.user_message}), exc.status
    return jsonify(payload)


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
