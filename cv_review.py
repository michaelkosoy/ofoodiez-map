"""AI CV review for the /hitech section.

GET  /hitech/cv-review      — upload page (app/templates/hitech_cv_review.html)
POST /api/hitech/cv-review  — multipart upload (field "cv", .pdf or .txt, <= 5 MB).
                              The CV is graded by Gemini against the Hebrew
                              job-search & CV guide (app/data/cv_guide_full.md)
                              and strict JSON feedback is returned.

Register in app.py with:
    from cv_review import cv_review_bp
    app.register_blueprint(cv_review_bp)
"""

import base64
import json
import os

import requests
from flask import Blueprint, jsonify, render_template, request

cv_review_bp = Blueprint('cv_review', __name__)

MAX_CV_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = ('.pdf', '.txt')

GUIDE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'app', 'data', 'cv_guide_full.md')

# Plain REST call: the google-generativeai SDK's grpc stack killed the single
# gunicorn worker on Render at first use, so we talk to the HTTP API directly.
GEMINI_URL = ('https://generativelanguage.googleapis.com/v1beta/'
              'models/gemini-2.5-flash:generateContent')

# Module-level cache, filled lazily on the first API request.
_guide_text = None

REVIEW_INSTRUCTIONS = """You are a strict but encouraging CV reviewer for junior developers and students trying to break into the Israeli high-tech industry.

You will receive two things:
1. THE GUIDE — the Ofoodiez job-search & CV guide, written in Hebrew. The guide is your ONLY rubric: grade the CV exclusively against the guide's rules. These include (non-exhaustively):
   - Exactly one page.
   - Written in English.
   - No photo, and no personal details such as ID number, age / date of birth, marital status or full home address.
   - Opens with a short "who I am & what I'm looking for" paragraph.
   - Technologies highlighted in bold.
   - Bullets built from strong action verbs with quantified impact, following the X-Y-Z formula ("Accomplished X, as measured by Y, by doing Z").
   - An honest skills list without self-ratings (no stars, percentages or "8/10").
   - For juniors without work experience: meaningful projects and a GitHub link.
   - AI shown integrated into real projects, not sprinkled as buzzwords.
2. THE CV to review — either a PDF file or plain text.

Review rules:
- Be strict about the guide's rules but encouraging in tone — the reader is a junior or a student.
- Quote specific lines from the CV, in their original language, as evidence wherever relevant.
- Every guide rule the CV violates must appear in "improvements"; things it does well per the guide belong in "strengths".
- ALL feedback text (verdict, strengths, improvements) MUST be written in Hebrew. Quoted CV lines stay in their original language.
- "score" is an integer from 0 to 100 reflecting overall compliance with the guide.
- Give 3-5 strengths and 4-8 improvements, with improvements ordered from highest to lowest impact.
- If the uploaded document is not actually a CV, give a low score and say so in the verdict (in Hebrew).

Respond with STRICT JSON only — no markdown, no code fences, no commentary before or after. Exactly this shape:
{"score": <int 0-100>, "verdict": "<one-line Hebrew summary>", "strengths": ["<Hebrew>", ...], "improvements": [{"area": "<Hebrew section name>", "issue": "<Hebrew, quoting the CV where relevant>", "fix": "<concrete Hebrew suggestion>"}, ...]}
"""


def _load_guide():
    """Read the Hebrew CV guide once and cache it for the process lifetime."""
    global _guide_text
    if _guide_text is None:
        with open(GUIDE_PATH, 'r', encoding='utf-8') as f:
            _guide_text = f.read()
    return _guide_text


def _api_key():
    """The Gemini API key from the environment, or None when unavailable."""
    key = os.environ.get('GEMINI_API_KEY')
    if not key or key == 'your_gemini_api_key_here':
        return None
    return key


def _strip_code_fences(text):
    """Remove ``` fences that models sometimes wrap JSON in despite instructions."""
    text = text.strip()
    if text.startswith('```'):
        newline = text.find('\n')
        text = text[newline + 1:] if newline != -1 else text[3:]
        text = text.strip()
        if text.endswith('```'):
            text = text[:-3].strip()
    return text


@cv_review_bp.route('/hitech/cv-review')
def cv_review_page():
    """The 'Review my CV with AI' page."""
    return render_template('hitech_cv_review.html',
                           active_hitech_page='cv-review', active_page='hitech')


@cv_review_bp.route('/api/hitech/cv-review', methods=['POST'])
def cv_review_api():
    """Grade an uploaded CV against the guide and return JSON feedback."""
    file = request.files.get('cv')
    if file is None or not file.filename:
        return jsonify({'error': 'No CV file received. Please attach a .pdf or .txt file.'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': 'Unsupported file type. Please upload a .pdf or .txt file.'}), 400

    file_bytes = file.read()
    if len(file_bytes) > MAX_CV_BYTES:
        return jsonify({'error': 'This file is over 5 MB. Please upload a smaller one.'}), 413
    if not file_bytes:
        return jsonify({'error': 'The uploaded file is empty.'}), 400

    key = _api_key()
    if key is None:
        return jsonify({'error': 'The AI reviewer is not configured on this server yet. Please try again later.'}), 503

    try:
        guide = _load_guide()
    except OSError:
        return jsonify({'error': 'The review guide is unavailable on this server. Please try again later.'}), 503

    prompt = (REVIEW_INSTRUCTIONS
              + '\n\n===== THE GUIDE (your grading rubric) =====\n\n'
              + guide
              + '\n\n===== END OF GUIDE =====\n')
    parts = [{'text': prompt}]
    if ext == '.pdf':
        parts.append({'inline_data': {'mime_type': 'application/pdf',
                                      'data': base64.b64encode(file_bytes).decode('ascii')}})
    else:
        cv_text = file_bytes.decode('utf-8', errors='replace')
        parts.append({'text': '===== THE CV TO REVIEW =====\n\n' + cv_text})

    payload = {
        'contents': [{'parts': parts}],
        'generationConfig': {'responseMimeType': 'application/json'},
    }
    try:
        resp = requests.post(GEMINI_URL, json=payload, timeout=90,
                             headers={'x-goog-api-key': key})
        resp.raise_for_status()
        raw = resp.json()['candidates'][0]['content']['parts'][0]['text']
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        return jsonify({'error': 'The AI reviewer could not process your CV right now. Please try again in a minute.'}), 502

    try:
        review = json.loads(_strip_code_fences(raw))
    except (ValueError, TypeError):
        review = None
    if not isinstance(review, dict) or 'score' not in review:
        return jsonify({'error': 'The AI reviewer returned an unexpected answer. Please try again.'}), 502

    return jsonify(review)
