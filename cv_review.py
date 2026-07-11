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
from flask import Blueprint, jsonify, render_template, request, session

cv_review_bp = Blueprint('cv_review', __name__)

MAX_CV_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = ('.pdf', '.txt')

GUIDE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'app', 'data', 'cv_guide_full.md')

# Plain REST call to the Gemini HTTP API (no SDK).
# Model is env-overridable; default is the price/performance pick for a
# rubric-grading task (~0.5 cent per review as of 2026-07).
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3.1-flash-lite')
GEMINI_URL = ('https://generativelanguage.googleapis.com/v1beta/'
              f'models/{GEMINI_MODEL}:generateContent')

# Module-level cache, filled lazily on the first API request.
_guide_text = None

REVIEW_INSTRUCTIONS = """You are a strict but encouraging CV reviewer for junior developers and students trying to break into the Israeli high-tech industry.

You will receive two things:
1. THE GUIDE — the Ofoodiez job-search & CV guide, written in Hebrew. The guide is your ONLY rubric: grade the CV exclusively against the guide's rules.
2. THE CV to review — either a PDF file or plain text.

THE CHECKLIST — verify the CV against it rule by rule. EVERY rule below MUST appear exactly once in the "checklist" array of your answer with a status of "pass", "partial" or "fail". Do not skip or merge rules:
1. "עמוד אחד" — the CV fits one page.
2. "באנגלית" — the CV is written in English.
3. "בלי תמונה ופרטים מיותרים" — no photo, age / birth date, ID number, marital status or full home address.
4. "טייטל מתחת לשם" — a short professional title under the name (e.g. Software Engineer, Computer Science Student).
5. "פסקת פתיחה" — a 2–4 line opening paragraph: who they are, what they bring (key technologies), what they look for.
6. "טכנולוגיות מודגשות" — technologies / keywords highlighted in bold throughout the document.
7. "פעלים חזקים ומספרים" — bullets start with strong action verbs and quantify impact (X-Y-Z formula: "Accomplished X, as measured by Y, by doing Z").
8. "רשימת כישורים כנה" — honest skills list: no self-ratings (stars, "8/10"), no office-suite filler, nothing they couldn't defend in an interview.
9. "פרויקטים ו-GitHub" — meaningful projects with working links (critical for juniors without work experience).
10. "AI משולב נכון" — AI appears integrated in real projects / work, not sprinkled as empty buzzwords.

Review rules:
- Be strict about the guide's rules but encouraging in tone — the reader is a junior or a student.
- Quote specific lines from the CV, in their original language, as evidence wherever relevant.
- Every "fail" or "partial" checklist rule must have a matching entry in "improvements"; things done well per the guide belong in "strengths".
- Each improvement MUST include a "rewrite": a concrete, ready-to-paste replacement written in English, built ONLY from details that actually appear in the CV — rephrase and restructure what exists, never invent experience, numbers or technologies. Where a real number is missing, put a placeholder like [X users] so the candidate fills it in.
- "action_items" is the candidate's to-do list: 4–7 short, imperative Hebrew steps ordered by impact (e.g. "מחקו את הגיל ואת שורת הממליצים", "הוסיפו שורת טייטל מתחת לשם").
- ALL feedback text (verdict, strengths, improvement issues/fixes, action items, checklist notes) MUST be written in Hebrew. Quoted CV lines and every "rewrite" stay in English.
- "score" is an integer from 0 to 100 reflecting overall compliance with the guide.
- Give 3-5 strengths and 4-8 improvements, with improvements ordered from highest to lowest impact.
- If the uploaded document is not actually a CV, give a low score and say so in the verdict (in Hebrew).

Respond with STRICT JSON only — no markdown, no code fences, no commentary before or after. Exactly this shape:
{"score": <int 0-100>, "verdict": "<one-line Hebrew summary>", "strengths": ["<Hebrew>", ...], "improvements": [{"area": "<Hebrew section name>", "issue": "<Hebrew, quoting the CV where relevant>", "fix": "<concrete Hebrew suggestion>", "rewrite": "<ready-to-paste English replacement based only on the CV's own content>"}, ...], "action_items": ["<Hebrew imperative step>", ...], "checklist": [{"rule": "<exact Hebrew rule name from the checklist>", "status": "pass|partial|fail", "note": "<short Hebrew note>"}, ...]}
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
    """The 'Review my CV with AI' page.

    ponytail: admin-session gate (same login as /admin) until public launch —
    visitors see a Coming soon card.
    """
    return render_template('hitech_cv_review.html',
                           active_hitech_page='cv-review', active_page='hitech',
                           locked=not session.get('admin_logged_in'))


@cv_review_bp.route('/api/hitech/cv-review', methods=['POST'])
def cv_review_api():
    """Grade an uploaded CV against the guide and return JSON feedback."""
    if not session.get('admin_logged_in'):
        return jsonify({'error': 'The AI reviewer is not open yet — coming soon.'}), 403

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
    # NOTE: never return 502/504 from here — Cloudflare replaces those bodies
    # with its own error page and the frontend loses our JSON message.
    try:
        resp = requests.post(GEMINI_URL, json=payload, timeout=90,
                             headers={'x-goog-api-key': key})
    except requests.RequestException as exc:
        print(f"❌ CV review: Gemini request failed: {exc}")
        return jsonify({'error': 'Could not reach the AI service. Please try again in a minute.'}), 503

    if resp.status_code != 200:
        print(f"❌ CV review: Gemini returned {resp.status_code}: {resp.text[:500]}")
        if resp.status_code == 429:
            msg = 'The AI reviewer is at capacity right now. Please try again in a few minutes.'
        else:
            msg = f'The AI reviewer is misconfigured on this server (upstream error {resp.status_code}).'
        return jsonify({'error': msg}), 503

    try:
        raw = resp.json()['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError, TypeError, ValueError):
        print(f"❌ CV review: unexpected Gemini response shape: {resp.text[:500]}")
        return jsonify({'error': 'The AI reviewer returned an unexpected answer. Please try again.'}), 503

    try:
        review = json.loads(_strip_code_fences(raw))
    except (ValueError, TypeError):
        review = None
    if not isinstance(review, dict) or 'score' not in review:
        return jsonify({'error': 'The AI reviewer returned an unexpected answer. Please try again.'}), 503

    return jsonify(review)
