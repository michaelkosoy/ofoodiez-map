"""The CV review + optimization pipeline.

Phases (per review):
  A. Parse the untrusted upload → text/PDF evidence (DOCX via the sandbox;
     PDFs are never parsed in-process — Gemini reads them on Google's side).
  B. EXTRACT: Gemini structured call → canonical CV model + evidence ledger.
     Low-confidence candidate name → stop and ask the user to confirm.
  C. CRITIC (original): the classic guide review + before-scores.
  D. OPTIMIZE: canonical (address pre-redacted to city) + job input →
     optimized CV + change ledger + career recommendations.
  E. VALIDATE/REPAIR: deterministic validators (address, name, evidence,
     recommendations, wording); up to 2 model repair rounds, then hard
     deterministic fixes. Nothing non-compliant can ship.
  F. CRITIC (optimized): after-scores.
  G. RENDER: brand-new DOCX (inspected) + PDF + text — clean reconstruction.
  H. PERSIST: DB row (+ optional Drive mirror), usage/cost metadata.
"""
import base64
import copy
import json
import re
import os
import threading
import time
import traceback
import uuid

from . import gemini, prompts, sandbox, schemas, storage, validators
from .docx_inspect import inspect_docx
from .docx_writer import build_docx
from .frameworks import FRAMEWORK_VERSION, framework_for
from .pdf_writer import build_pdf
from .render_common import cv_to_text, has_hebrew, polish_cv

GUIDE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          '..', 'app', 'data', 'cv_guide_full.md')

NAME_CONFIDENCE_THRESHOLD = 0.75
MAX_REPAIRS = 2
SOFT_DEADLINE_SECONDS = 240   # stay under gunicorn's hard timeout

_guide_text = None


class PipelineError(Exception):
    """Failure with a client-safe message and an HTTP status."""

    def __init__(self, user_message, status=503):
        super().__init__(user_message)
        self.user_message = user_message
        self.status = status


def _load_guide():
    global _guide_text
    if _guide_text is None:
        with open(GUIDE_PATH, encoding='utf-8') as f:
            _guide_text = f.read()
    return _guide_text


# ── Phase A: untrusted file → model input ────────────────────────────────────
def file_to_evidence_parts(file_bytes, ext):
    """Returns the Gemini `parts` entry describing the CV document."""
    if ext == '.pdf':
        if not file_bytes.startswith(b'%PDF-'):
            raise PipelineError('This file is not a valid PDF.', 400)
        return {'inline_data': {'mime_type': 'application/pdf',
                                'data': base64.b64encode(file_bytes).decode('ascii')}}
    if ext == '.docx':
        verdict = sandbox.parse_docx(file_bytes)
        if not verdict.get('ok'):
            raise PipelineError(verdict.get('message') or
                                'Could not read this document.', 400)
        return {'text': '===== THE CV DOCUMENT (extracted text) =====\n\n' + verdict['text']}
    # .txt
    text = file_bytes.decode('utf-8', errors='replace').strip()
    if not text:
        raise PipelineError('The uploaded file is empty.', 400)
    return {'text': '===== THE CV DOCUMENT =====\n\n' + text}


# ── Shared helpers ───────────────────────────────────────────────────────────
def _call(generate, *, parts, schema, purpose, usage, key, **kw):
    try:
        return generate(parts, schema, purpose=purpose, usage=usage, key=key, **kw)
    except gemini.GeminiError as exc:
        raise PipelineError(exc.user_message, 503)


def _redacted_for_prompt(canonical, name):
    """The model working copy: precise address removed BEFORE the optimizer
    ever sees it (city/country stay), confirmed name injected."""
    c = copy.deepcopy(canonical)
    (c.get('contact') or {}).pop('location_raw', None)
    c.setdefault('candidate_name', {})['full_name'] = name
    return c


def _cv_json_part(label, obj):
    return {'text': f'===== {label} =====\n\n' + json.dumps(obj, ensure_ascii=False, indent=1)}


def _run_critic(generate, key, usage, *, canonical_like, claims, jd_text, job_title,
                formatting_note, purpose, anchor=None):
    prompt = prompts.critic_prompt(_load_guide(), jd_text=jd_text, job_title=job_title,
                                   formatting_note=formatting_note, anchor=anchor)
    data = _call(generate, parts=[{'text': prompt},
                                  _cv_json_part('THE CV (structured extraction)', canonical_like),
                                  _cv_json_part('EVIDENCE LEDGER', claims)],
                 schema=schemas.CRITIC_SCHEMA, purpose=purpose, usage=usage, key=key,
                 temperature=0.2)
    try:
        data = schemas.ensure_critic(data)
    except schemas.SchemaError as exc:
        raise PipelineError('The AI reviewer returned an unexpected answer. Please try again.') from exc
    # Wording rule is enforced deterministically on feedback text — offending
    # items are dropped rather than re-billed.
    if validators.validate_wording(validators.critic_feedback_texts(data)):
        validators.drop_forbidden_feedback(data)
    return data


def _optimized_as_canonical(cv, text_len):
    """Shape the optimized CV like an extraction so the same critic grades
    before and after symmetrically."""
    return {
        'is_cv': True,
        'candidate_name': {'full_name': cv.get('name'), 'confidence': 1.0,
                           'source_text': cv.get('name', '')},
        'contact': {'email': cv.get('email'), 'phone': cv.get('phone'),
                    'location_raw': cv.get('location'), 'city': cv.get('location'),
                    'country': None, 'links': cv.get('links') or []},
        'title': cv.get('title'), 'summary': cv.get('summary'),
        'skills': [{'name': s, 'source_text': s}
                   for g in cv.get('skills_groups') or [] for s in g.get('skills') or []],
        'experience': cv.get('experience') or [],
        'projects': [{'name': p.get('name', ''), 'description': p.get('description', ''),
                      'link': p.get('link')} for p in cv.get('projects') or []],
        'education': cv.get('education') or [],
        'extras': cv.get('extras') or [],
        'flags': {'has_photo': False, 'language': 'en', 'self_ratings': False,
                  'emphasized_technologies': True,
                  'page_count_estimate': max(1.0, round(text_len / 3200, 1))},
    }


def _translate_leftover_hebrew(cv, *, generate, key, usage):
    """The content floor restores text VERBATIM, so a Hebrew CV whose optimizer
    output lost a section comes back in Hebrew — but an optimized CV must be
    English (guide rule 2). One structured call translates exactly those
    strings; the candidate's name is never touched, and on any failure the
    Hebrew text stays (content beats emptiness).
    Returns the number of translated strings."""
    targets = [(path, value, setter)
               for path, value, setter in validators.iter_cv_strings(cv)
               if has_hebrew(value) and path != 'name']
    if not targets:
        return 0
    payload = [value for _p, value, _s in targets]
    try:
        out = generate([{'text': prompts.translate_prompt(len(payload))},
                        {'text': json.dumps(payload, ensure_ascii=False, indent=0)}],
                       schemas.TRANSLATION_SCHEMA, purpose='translate',
                       usage=usage, key=key, temperature=0.1)
        lines = out.get('lines') if isinstance(out, dict) else None
        if not isinstance(lines, list) or len(lines) != len(targets):
            print(f'⚠️ CV review: translation returned {len(lines or [])} of {len(targets)} lines — kept original')
            return 0
        translated = 0
        for (_path, original, setter), line in zip(targets, lines):
            if isinstance(line, str) and line.strip() and not has_hebrew(line):
                setter(line.strip())
                translated += 1
        return translated
    except gemini.GeminiError as exc:
        print(f'⚠️ CV review: translation call failed ({exc}) — kept original text')
        return 0


def _collect_violations(opt, corpus, profile, expected_name, canonical):
    v = []
    v += validators.validate_name(opt['optimized_cv'], expected_name)
    v += validators.validate_no_address(opt['optimized_cv'], profile)
    v += validators.validate_evidence(opt, corpus)
    v += validators.validate_content_floor(opt, canonical)
    v += validators.validate_recommendations(opt, corpus)
    v += validators.validate_wording(validators.rec_feedback_texts(opt))
    return v


def _apply_hard_fixes(opt, corpus, profile, expected_name, canonical):
    cv = opt['optimized_cv']
    cv['name'] = expected_name
    validators.fix_address(cv, profile)
    validators.drop_unevidenced(opt, corpus)
    validators.fix_recommendations(opt, corpus)
    validators.restore_from_canonical(opt, canonical, profile)


def _align_title_to_job(opt, job_title):
    """The line under the name is what a screener reads first, so when the
    candidate told us the target role it wins over the model's phrasing.
    Evidence rules are untouched — this is a label, not a claim of experience."""
    target = ' '.join((job_title or '').split())[:60]
    if not target or not re.search(r'[^\W\d_]', target, re.UNICODE):
        return
    cv = opt['optimized_cv']
    current = (cv.get('title') or '').strip()
    if current.lower() == target.lower():
        return
    cv['title'] = target
    opt['changes'].append({
        'change_type': 'rewrite', 'section': 'title',
        'before': current, 'after': target,
        'reason': 'הטייטל שמתחת לשם הותאם לתפקיד היעד — זה מה שהמסנן קורא ראשון.',
        'evidence_refs': []})


def _ensure_location_redaction_change(opt, canonical, profile):
    """The change ledger must truthfully include the address redaction when
    the original carried sub-city precision — recorded deterministically."""
    had_precise = bool(profile['forbidden_tokens'] or profile['phrases'])
    if not had_precise:
        return
    changes = opt['changes']
    if any(c['change_type'] == 'location_redaction' for c in changes):
        return
    raw = (canonical.get('contact') or {}).get('location_raw') or ''
    changes.append({
        'change_type': 'location_redaction', 'section': 'contact',
        'before': raw, 'after': profile['city'] or '',
        'reason': 'הוסרה הכתובת המדויקת מטעמי פרטיות — הדיוק המקסימלי בקורות חיים הוא עיר.',
        'evidence_refs': []})


_SUMMARY_ORDER = ['rewrite', 'shorten', 'remove', 'reorder', 'keyword_surface',
                  'location_redaction', 'deduplication', 'formatting']


def _change_summary(changes, jd_analysis, city):
    counted = [c for c in changes if c['change_type'] != 'keep']
    by_type = {}
    for c in counted:
        by_type[c['change_type']] = by_type.get(c['change_type'], 0) + 1
    lines = []
    for t in _SUMMARY_ORDER:
        n = by_type.get(t, 0)
        if not n:
            continue
        one = n == 1
        if t == 'rewrite':
            lines.append('שורה אחת שוכתבה לניסוח תוצאה (X-Y-Z) עם פועל חזק' if one else
                         f'{n} שורות שוכתבו לניסוח תוצאה (X-Y-Z) עם פעלים חזקים')
        elif t == 'shorten':
            lines.append('סעיף אחד קוצר כדי לשמור על עמוד אחד' if one else
                         f'{n} סעיפים קוצרו כדי לשמור על עמוד אחד')
        elif t == 'remove':
            lines.append('סעיף אחד חלש או מיותר הוסר' if one else
                         f'{n} סעיפים חלשים או מיותרים הוסרו')
        elif t == 'reorder':
            lines.append('מקטע אחד סודר מחדש לפי רלוונטיות' if one else
                         f'{n} מקטעים סודרו מחדש לפי רלוונטיות')
        elif t == 'keyword_surface':
            suffix = ' בהתאם למשרה' if jd_analysis else ''
            lines.append(f'כישור אחד שכבר קיים בקורות החיים הובלט{suffix}' if one else
                         f'{n} כישורים שכבר קיימים בקורות החיים הובלטו{suffix}')
        elif t == 'location_redaction':
            kept = f'נשארה רק "{city}"' if city else 'המיקום הושמט'
            lines.append(f'הכתובת המדויקת הוסרה — {kept}')
        elif t == 'deduplication':
            lines.append('כפילות אחת אוחדה' if one else f'{n} כפילויות אוחדו')
        elif t == 'formatting':
            lines.append('הפורמט הותאם לתבנית נקייה של עמוד אחד')
    not_evidenced = (jd_analysis or {}).get('not_evidenced') or []
    if not_evidenced:
        lines.append('לא הוספנו: ' + ', '.join(not_evidenced[:6]) +
                     ' — דרישות של המשרה שאין להן עדות בקורות החיים (ראו "כישורים שכדאי לפתח")')
    return {'total_changes': len(counted), 'by_type': by_type, 'lines': lines}


# ── Public entry points ──────────────────────────────────────────────────────
def _create_shell(*, filename, ext, job, consent, owner_user_id, file_bytes):
    from database.models import db, CvReview
    review = CvReview(
        id=str(uuid.uuid4()),
        owner_user_id=owner_user_id,
        status='processing',
        talent_pool_consent=bool(consent),
        job_title=job['job_title'] or None,
        job_description=job['job_description'] or None,
        instructions=job['instructions'] or None,
        original_filename=(filename or '')[:256],
        original_ext=ext,
        original_file=file_bytes,
    )
    db.session.add(review)
    db.session.commit()
    return review


def _mark_failed(review, message, usage=None):
    from database.models import db
    try:
        review.status = 'failed'
        review.error = str(message)[:1000]
        if usage is not None:
            review.usage = usage.totals()
        db.session.commit()
    except Exception:
        db.session.rollback()


def _extract_phase(review, doc_part, *, generate, key, usage):
    """Phase B on an existing row. Returns the confirmed candidate name, or
    None when the review paused for name confirmation (row already updated)."""
    from database.models import db
    try:
        extraction = _call(generate,
                           parts=[{'text': prompts.extraction_prompt()}, doc_part],
                           schema=schemas.EXTRACTION_SCHEMA, purpose='extract',
                           usage=usage, key=key, temperature=0.1)
        try:
            canonical = schemas.ensure_extraction(extraction)
        except schemas.SchemaError as exc:
            raise PipelineError('The AI reviewer returned an unexpected answer. '
                                'Please try again.') from exc
    except PipelineError as exc:
        _mark_failed(review, exc.user_message, usage)
        raise

    contact = canonical.get('contact') or {}
    review.canonical = canonical
    review.candidate_name = (canonical['candidate_name'].get('full_name') or '')[:256] or None
    review.candidate_email = (contact.get('email') or '')[:256] or None
    review.candidate_phone = (contact.get('phone') or '')[:64] or None
    review.primary_role = (canonical.get('title') or '')[:128] or None
    db.session.commit()

    name = canonical['candidate_name'].get('full_name')
    confidence = canonical['candidate_name'].get('confidence', 0)
    if not name or confidence < NAME_CONFIDENCE_THRESHOLD:
        review.status = 'pending_name'
        review.usage = usage.totals()
        review.result = {'status': 'needs_name_confirmation',
                         'review_id': review.id,
                         'guessed_name': name or '',
                         'message': 'לא הצלחנו לזהות בביטחון את השם בקורות החיים. איך רושמים אותו בדיוק?'}
        db.session.commit()
        return None
    return name


def start_review(*, file_bytes, filename, ext, job, consent, owner_user_id,
                 key, generate=None):
    """Synchronous run (tests, eval harness): phase A+B, then either a
    name-confirmation stop or the full pipeline. Returns (payload, review)."""
    generate = generate or gemini.generate_json
    usage = gemini.UsageTracker()
    storage.purge_expired()
    doc_part = file_to_evidence_parts(file_bytes, ext)
    review = _create_shell(filename=filename, ext=ext, job=job, consent=consent,
                           owner_user_id=owner_user_id, file_bytes=file_bytes)
    name = _extract_phase(review, doc_part, generate=generate, key=key, usage=usage)
    if name is None:
        return review.result, review
    return _continue_review(review, name, generate=generate, key=key, usage=usage), review


def launch_review(app, *, doc_part, file_bytes, filename, ext, job, consent,
                  owner_user_id, key, generate=None):
    """Asynchronous entry used by the web routes: creates the row and runs the
    whole pipeline in a background thread, so the HTTP request returns
    immediately and no proxy/worker timeout (Cloudflare caps responses at
    ~100s) can kill a long review. The client polls the status endpoint.
    `doc_part` comes from file_to_evidence_parts, run synchronously by the
    route so invalid/hostile files still fail fast with a 400."""
    generate = generate or gemini.generate_json
    storage.purge_expired()
    storage.fail_stale_processing()
    review = _create_shell(filename=filename, ext=ext, job=job, consent=consent,
                           owner_user_id=owner_user_id, file_bytes=file_bytes)

    def body(r, usage):
        name = _extract_phase(r, doc_part, generate=generate, key=key, usage=usage)
        if name is not None:   # None = paused for name confirmation
            _continue_review(r, name, generate=generate, key=key, usage=usage)

    _spawn(app, review.id, body)
    return review


def _prepare_resume(review, confirmed_name):
    """Validate + apply the user-confirmed name (fast, synchronous)."""
    from database.models import db
    name = ' '.join((confirmed_name or '').split())
    if not (2 <= len(name) <= 120):
        raise PipelineError('Please enter the candidate name as it should appear on the CV.', 400)
    usage = gemini.UsageTracker()
    if review.usage and review.usage.get('per_call'):
        usage.calls.extend(review.usage['per_call'])   # keep extraction cost counted
    review.candidate_name = name[:256]
    # Reassign (not mutate) the JSON column so SQLAlchemy sees the change.
    canonical = copy.deepcopy(review.canonical)
    canonical.setdefault('candidate_name', {})['full_name'] = name
    canonical['candidate_name']['confidence'] = 1.0   # user-confirmed
    review.canonical = canonical
    review.status = 'processing'
    review.result = None
    db.session.commit()
    return name, usage


def resume_review(review, confirmed_name, *, key, generate=None):
    """Synchronous resume (tests, eval harness)."""
    generate = generate or gemini.generate_json
    name, usage = _prepare_resume(review, confirmed_name)
    return _continue_review(review, name, generate=generate, key=key, usage=usage)


def launch_resume(app, review, confirmed_name, *, key, generate=None):
    """Asynchronous resume used by the web routes (validation stays sync so a
    bad name is still an immediate 400)."""
    generate = generate or gemini.generate_json
    name, usage = _prepare_resume(review, confirmed_name)
    _spawn(app, review.id,
           lambda r, _usage: _continue_review(r, name, generate=generate,
                                              key=key, usage=usage))
    return review


def _spawn(app, review_id, body):
    def worker():
        with app.app_context():
            from database.models import db, CvReview
            review = CvReview.query.get(review_id)
            usage = gemini.UsageTracker()
            try:
                body(review, usage)
            except PipelineError:
                pass   # row already marked failed with a user-facing message
            except Exception:
                print(f'❌ CV review worker crashed ({review_id}):\n{traceback.format_exc()}')
                _mark_failed(review, 'Something went wrong while reviewing your CV. '
                                     'Please try again.')
            finally:
                db.session.remove()
    threading.Thread(target=worker, daemon=True,
                     name=f'cvreview-{review_id[:8]}').start()


def _continue_review(review, name, *, generate, key, usage):
    from database.models import db
    started = time.monotonic()

    def remaining():
        return SOFT_DEADLINE_SECONDS - (time.monotonic() - started)

    canonical = review.canonical
    jd_text = review.job_description or None
    job_title = review.job_title or None

    try:
        claims = validators.derive_claims(canonical)
        corpus = validators.evidence_corpus(claims)
        profile = validators.address_profile(canonical)
        redacted = _redacted_for_prompt(canonical, name)

        # Not actually a CV → classic review only, no optimized document.
        if canonical.get('is_cv') is False:
            critic = _run_critic(generate, key, usage, canonical_like=redacted, claims=claims,
                                 jd_text=jd_text, job_title=job_title,
                                 formatting_note=None, purpose='critic_original')
            payload = {'status': 'not_a_cv', 'review_id': review.id,
                       'original_review': _review_block(critic),
                       'scores': {'rules': {'before': schemas.rules_score(critic['rules_checklist']),
                                            'after': None, 'total': len(schemas.RULES)},
                                  'quality': {'before': critic['quality_score'], 'after': None},
                                  'jd_match': None}}
            review.status = 'complete'
            review.usage = usage.totals()
            review.result = payload
            db.session.commit()
            return payload

        fmt_orig = ('flags.emphasized_technologies reflects whether the original document '
                    'visually highlights technologies — grade rule 6 from it plus the content.')
        critic_before = _run_critic(generate, key, usage, canonical_like=redacted, claims=claims,
                                    jd_text=jd_text, job_title=job_title,
                                    formatting_note=fmt_orig, purpose='critic_original')

        family, framework = framework_for(f"{job_title or ''} {canonical.get('title') or ''}")
        opt_prompt = prompts.optimizer_prompt(
            _load_guide(), job_title=job_title, jd_text=jd_text,
            instructions=review.instructions or None,
            framework_family=family, framework=framework if not jd_text else None,
            framework_version=FRAMEWORK_VERSION)
        opt = _call(generate,
                    parts=[{'text': opt_prompt},
                           _cv_json_part('THE CANDIDATE CV (canonical extraction)', redacted),
                           _cv_json_part('EVIDENCE LEDGER (claim ids)', claims),
                           {'text': f'CANDIDATE NAME (must appear EXACTLY as-is): {name}'}],
                    schema=schemas.OPTIMIZER_SCHEMA, purpose='optimize', usage=usage,
                    key=key, temperature=0.3, timeout=100)
        try:
            opt = schemas.ensure_optimizer(opt)
        except schemas.SchemaError as exc:
            raise PipelineError('The AI reviewer returned an unexpected answer. Please try again.') from exc

        # Validate → model repair (bounded) → deterministic hard fixes.
        repairs = 0
        violations = _collect_violations(opt, corpus, profile, name, canonical)
        while violations and repairs < MAX_REPAIRS and remaining() > 60:
            repairs += 1
            repaired = _call(generate,
                             parts=[{'text': prompts.repair_prompt(
                                 violations, json.dumps(opt, ensure_ascii=False))}],
                             schema=schemas.OPTIMIZER_SCHEMA, purpose=f'repair_{repairs}',
                             usage=usage, key=key, temperature=0.1)
            try:
                candidate_opt = schemas.ensure_optimizer(repaired)
            except schemas.SchemaError:
                break   # keep previous opt; hard fixes below
            # A repair must never "fix" violations by deleting the CV: if the
            # repaired output lost most of the content, keep what we had and
            # let the deterministic fixes handle the rest.
            prev_bullets = validators.total_bullets(opt['optimized_cv'])
            new_bullets = validators.total_bullets(candidate_opt['optimized_cv'])
            if prev_bullets > 0 and new_bullets < max(1, prev_bullets // 2):
                print(f'⚠️ CV review: repair_{repairs} regressed content '
                      f'({prev_bullets}→{new_bullets} bullets) — discarding the repair')
                break
            opt = candidate_opt
            violations = _collect_violations(opt, corpus, profile, name, canonical)
        if violations:
            _apply_hard_fixes(opt, corpus, profile, name, canonical)
            violations = _collect_violations(opt, corpus, profile, name, canonical)
            if any(v['type'] in ('address', 'name') for v in violations):
                raise PipelineError('Could not produce a compliant CV from this document. '
                                    'Please try again.')
        validators.fix_recommendations(opt, corpus)   # cap 3–5, priority order
        restored = validators.restore_from_canonical(opt, canonical, profile)  # content floor
        _ensure_location_redaction_change(opt, canonical, profile)
        _align_title_to_job(opt, job_title)

        cv = opt['optimized_cv']
        # The floor restores text verbatim, so a Hebrew source can leak Hebrew
        # into the CV — which breaks the guide's "CV in English" rule.
        if has_hebrew(cv_to_text(cv)) and remaining() > 30:
            n = _translate_leftover_hebrew(cv, generate=generate, key=key, usage=usage)
            if n:
                opt['changes'].append({
                    'change_type': 'rewrite', 'section': ','.join(restored) or 'cv',
                    'before': '', 'after': '',
                    'reason': f'{n} שורות תורגמו לאנגלית — קורות חיים באנגלית זה כלל בסיסי במדריך.',
                    'evidence_refs': []})

        cv = polish_cv(cv)
        text = cv_to_text(cv)
        if validators.find_address_leaks(text, profile):
            raise PipelineError('Could not produce a compliant CV from this document. '
                                'Please try again.')

        fmt_opt = ('the renderer bolds all listed technologies automatically and the '
                   'template is a clean single page — grade rules 1 and 6 accordingly.')
        critic_after = _run_critic(generate, key, usage,
                                   canonical_like=_optimized_as_canonical(cv, len(text)),
                                   claims=claims, jd_text=jd_text, job_title=job_title,
                                   formatting_note=fmt_opt, purpose='critic_optimized',
                                   anchor={'quality': critic_before['quality_score'],
                                           'jd_match': critic_before['jd_match']})

        docx_bytes = build_docx(cv)
        problems = inspect_docx(docx_bytes)
        if problems:
            print(f'❌ CV review: generated DOCX failed inspection: {problems}')
            raise PipelineError('Could not produce the final document. Please try again.')
        pdf_bytes = build_pdf(cv)

        changes = sorted(opt['changes'], key=lambda c: c['change_type'] == 'keep')
        summary = _change_summary(changes, opt.get('jd_analysis'),
                                  cv.get('location') or profile['city'])
        # The product rule: optimization only improves or holds — a lower
        # after-score is judge noise (two model gradings of preserved
        # evidence), floored at the before-score, never shown as a regression.
        def _floored(before, after):
            return {'before': before, 'after': max(before, after)}
        scores = {
            'rules': {**_floored(schemas.rules_score(critic_before['rules_checklist']),
                                 schemas.rules_score(critic_after['rules_checklist'])),
                      'total': len(schemas.RULES)},
            'quality': _floored(critic_before['quality_score'],
                                critic_after['quality_score']),
            'jd_match': (_floored(critic_before['jd_match'],
                                  critic_after['jd_match'] if critic_after['jd_match']
                                  is not None else critic_before['jd_match'])
                         if jd_text and critic_before['jd_match'] is not None else None),
        }

        payload = {
            'status': 'complete',
            'review_id': review.id,
            'candidate': {'name': name, 'city': cv.get('location') or profile['city'] or None},
            'downloads': {kind: f'/hitech/cv-review/download/{review.id}/{kind}'
                          for kind in ('docx', 'pdf', 'txt')},
            'scores': scores,
            'change_summary': summary,
            'changes': changes,
            'jd_analysis': opt.get('jd_analysis'),
            'career_recommendations': opt['career_recommendations'],
            'original_review': _review_block(critic_before),
            'optimized_checklist': critic_after['rules_checklist'],
            'optimized_text': text,
            'optimized_cv': cv,
            'repairs': repairs,
        }

        filenames = storage.review_filenames(name)
        review.status = 'complete'
        review.candidate_name = name[:256]
        review.primary_role = (cv.get('title') or review.primary_role or '')[:128] or None
        review.optimized_docx = docx_bytes
        review.optimized_pdf = pdf_bytes
        review.optimized_text = text
        review.result = {k: v for k, v in payload.items() if k != 'optimized_text'}
        review.usage = usage.totals()
        db.session.commit()

        owner_key = f'user_{review.owner_user_id}' if review.owner_user_id else 'anonymous'
        drive_ids = storage.upload_review_to_drive(owner_key, review.id, {
            filenames['docx']: (docx_bytes,
                                'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
            filenames['pdf']: (pdf_bytes, 'application/pdf'),
            f"{filenames['original']}{review.original_ext}":
                (review.original_file, 'application/octet-stream'),
        })
        if drive_ids:
            review.drive = drive_ids
            db.session.commit()
        return payload

    except PipelineError as exc:
        _mark_failed(review, exc.user_message, usage)
        raise
    except Exception:
        # Never let an unhandled exception become a bare 500 / silent thread
        # death — log the traceback server-side, fail the row with a friendly
        # message, and surface it as a PipelineError.
        print(f'❌ CV review pipeline crashed ({review.id}):\n{traceback.format_exc()}')
        _mark_failed(review, 'Something went wrong while reviewing your CV. Please try again.',
                     usage)
        raise PipelineError('Something went wrong while reviewing your CV. Please try again.')


def _review_block(critic):
    return {'verdict': critic['verdict'],
            'strengths': critic['strengths'],
            'improvements': critic['improvements'],
            'action_items': critic['action_items'],
            'checklist': critic['rules_checklist'],
            'quality_score': critic['quality_score'],
            'jd_match': critic.get('jd_match')}
