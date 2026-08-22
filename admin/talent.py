"""Talent Inbox admin dashboard — pages + JSON API.

Everything lives behind the existing admin auth (@login_required). CV files
are served ONLY through /admin/talent/cv/<id>/file — no public URLs ever (§6).
All outbound actions (referral emails, link emails) are explicit two-step
admin actions: preview, then send (§8) — nothing is ever sent automatically.

Scale note (ponytail): list pages pull up to 1000 candidates and assemble in
Python — 3-4 batched queries total, no N+1 (searching inside the JSON analysis
cross-dialect is what pushes filtering into Python). Add SQL-side filtering +
pagination if the pool outgrows that.
"""
import os
import re
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import (Response, current_app, jsonify, render_template, request,
                   session)
from sqlalchemy.orm import defer

from database.models import db
from talent import config as tcfg
from talent import emails as temails
from talent.ingest import sync_gmail
from talent.matching import plausible, run_reverse_matching
from talent.models import (CANDIDATE_STATUSES, FIT_LEVELS, REFERRAL_METHODS,
                           REFERRAL_STATUSES, TalentAiLog, TalentCandidate,
                           TalentCompany, TalentCv, TalentEmail, TalentMatch,
                           TalentReferral)
from talent.pipeline import (UploadError, add_cv, analyze_pending_async,
                             ensure_candidate)

from . import admin_bp
from .auth import login_required

# ---------------------------------------------------------------------------
# Shared assembly helpers
# ---------------------------------------------------------------------------

_CV_META = (defer(TalentCv.file), defer(TalentCv.text))


def _err(msg, code=400):
    return jsonify({'error': msg}), code


def _human_date(dt):
    if not dt:
        return ''
    today = datetime.utcnow().date()
    d = dt.date()
    if d == today:
        return 'Today'
    if d == today - timedelta(days=1):
        return 'Yesterday'
    return dt.strftime('%b %-d') if d.year == today.year else dt.strftime('%b %-d, %Y')


def _gmail_link(message_id):
    if not message_id or message_id.startswith('<synthetic-'):
        return ''
    return ('https://mail.google.com/mail/u/0/#search/rfc822msgid:'
            + quote(message_id.strip('<>'), safe=''))


def _active_cvs(candidate_ids):
    """Active CV per candidate, file/text blobs deferred. One IN query."""
    if not candidate_ids:
        return {}
    rows = TalentCv.query.options(*_CV_META).filter(
        TalentCv.candidate_id.in_(candidate_ids),
        TalentCv.is_active.is_(True)).all()
    return {cv.candidate_id: cv for cv in rows}


def _grouped(rows, key):
    out = {}
    for r in rows:
        out.setdefault(key(r), []).append(r)
    return out


def _candidate_views(cands):
    """Assemble the dashboard/list view model with 4 batched queries."""
    ids = [c.id for c in cands]
    cvs = _active_cvs(ids)
    matches = _grouped(
        TalentMatch.query.filter(TalentMatch.candidate_id.in_(ids)).all()
        if ids else [], lambda m: m.candidate_id)
    refs = _grouped(
        TalentReferral.query.filter(TalentReferral.candidate_id.in_(ids)).all()
        if ids else [], lambda r: r.candidate_id)
    views = []
    for c in cands:
        cv = cvs.get(c.id)
        a = (cv.analysis or {}) if cv else {}
        m = matches.get(c.id, [])
        r = refs.get(c.id, [])
        ref_statuses = {x.status for x in r}
        views.append({
            'c': c, 'cv': cv, 'a': a,
            'role': a.get('current_title') or c.current_title
                    or (a.get('roles') or [''])[0],
            'skills': a.get('skills') or [],
            'ai_rating': a.get('rating') or '',
            'match_count': sum(1 for x in m
                               if (x.admin_fit or x.ai_fit) in ('STRONG', 'MAYBE')),
            'has_referrals': bool(r),
            'needs_action': 'NEEDS_ACTION' in ref_statuses,
            'waiting': 'WAITING' in ref_statuses,
            'submitted': 'SUBMITTED' in ref_statuses,
            'ref_completed': 'COMPLETED' in ref_statuses,
            'received': _human_date(c.created_at),
            'analysis_status': cv.analysis_status if cv else 'none',
        })
    return views


def _bucket(v, key):
    """Does one candidate view fall into a counter/filter bucket?"""
    c = v['c']
    # "New" = no action taken at all: never reviewed (status NEW) AND never
    # referred anywhere.
    is_new = c.status == 'NEW' and not v['has_referrals']
    return {
        'new': is_new,
        'strong': c.status == 'STRONG',
        'maybe': c.status == 'MAYBE',
        'skip': c.status == 'SKIP',
        'needs_review': is_new and v['analysis_status'] in ('complete', 'failed'),
        'needs_action': v['needs_action'],
        'waiting': v['waiting'],
        'submitted': v['submitted'],
        'completed': c.status == 'COMPLETED' or v['ref_completed'],
        'archived': c.status == 'ARCHIVED',
        'all': c.status != 'ARCHIVED',
    }.get(key, True)


def _counters(views):
    keys = ('new', 'strong', 'maybe', 'skip', 'needs_review', 'needs_action',
            'waiting', 'submitted', 'completed')
    return {k: sum(1 for v in views if _bucket(v, k)) for k in keys}


def _text_blob(v):
    a = v['a']
    return ' '.join([
        v['c'].name or '', v['c'].email or '', v['role'] or '',
        ' '.join(a.get('roles') or []), ' '.join(v['skills']),
        a.get('summary') or '']).lower()


def _apply_filters(views, args):
    status = (args.get('status') or 'all').lower()
    views = [v for v in views if _bucket(v, status)]
    if args.get('q'):
        q = args['q'].lower().strip()
        views = [v for v in views if q in _text_blob(v)]
    if args.get('tech'):
        t = args['tech'].lower().strip()
        views = [v for v in views if any(t in s.lower() for s in v['skills'])]
    if args.get('role'):
        r = args['role'].lower().strip()
        views = [v for v in views
                 if r in (v['role'] or '').lower()
                 or any(r in x.lower() for x in (v['a'].get('roles') or []))]
    if args.get('seniority'):
        s = args['seniority'].upper()
        views = [v for v in views
                 if (v['a'].get('seniority') or v['c'].seniority or '').upper() == s]
    if args.get('source'):
        views = [v for v in views if (v['c'].source or '') == args['source']]
    if args.get('company'):
        try:
            cid = int(args['company'])
        except ValueError:
            cid = None
        if cid:
            cand_ids = {m.candidate_id for m in TalentMatch.query.filter_by(
                company_id=cid).all()}
            cand_ids |= {r.candidate_id for r in TalentReferral.query.filter_by(
                company_id=cid).all()}
            views = [v for v in views if v['c'].id in cand_ids]
    if args.get('since'):
        try:
            cutoff = datetime.utcnow() - timedelta(days=int(args['since']))
            views = [v for v in views if v['c'].created_at
                     and v['c'].created_at >= cutoff]
        except ValueError:
            pass
    return views


def _all_candidates():
    return TalentCandidate.query.order_by(
        TalentCandidate.created_at.desc()).limit(1000).all()


def _parse_list(value):
    """Accept a JSON list or a comma/newline-separated string."""
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r'[,\n]', str(value or ''))
    return [s.strip()[:128] for s in items if s and s.strip()][:50]


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@admin_bp.route('/talent')
@login_required
def talent_dashboard():
    views = _candidate_views(_all_candidates())
    counters = _counters(views)
    filtered = _apply_filters(views, request.args)
    companies = TalentCompany.query.order_by(TalentCompany.name).all()
    sources = sorted({v['c'].source for v in views if v['c'].source})
    gmail_ready = bool(tcfg.gmail_config()['user'] and tcfg.gmail_config()['password'])
    return render_template('admin/talent.html', views=filtered, counters=counters,
                           companies=companies, sources=sources,
                           args=request.args, gmail_ready=gmail_ready,
                           total=len(views))


@admin_bp.route('/talent/needs-action')
@login_required
def talent_needs_action():
    refs = TalentReferral.query.filter(
        TalentReferral.status.in_(('NEEDS_ACTION', 'WAITING'))) \
        .order_by(TalentReferral.created_at).all()
    cand_ids = list({r.candidate_id for r in refs})
    cands = {c.id: c for c in TalentCandidate.query.filter(
        TalentCandidate.id.in_(cand_ids)).all()} if cand_ids else {}
    comps = {c.id: c for c in TalentCompany.query.all()}
    groups = {'MANUAL_UPLOAD': [], 'REFERRAL_LINK': [], 'EMAIL': [], 'WAITING': []}
    for r in refs:
        item = {'r': r, 'cand': cands.get(r.candidate_id),
                'comp': comps.get(r.company_id)}
        if r.status == 'WAITING':
            groups['WAITING'].append(item)
        else:
            groups.setdefault(r.method or 'MANUAL_UPLOAD', []).append(item)
    review_views = [v for v in _candidate_views(_all_candidates())
                    if _bucket(v, 'needs_review')]
    return render_template('admin/talent_needs_action.html', groups=groups,
                           review_views=review_views)


@admin_bp.route('/talent/candidate/<cand_id>')
@login_required
def talent_candidate(cand_id):
    cand = db.session.get(TalentCandidate, cand_id)
    if cand is None:
        return 'Candidate not found', 404
    cvs = TalentCv.query.options(*_CV_META).filter_by(candidate_id=cand.id) \
        .order_by(TalentCv.version.desc()).all()
    active_cv = next((cv for cv in cvs if cv.is_active), None)
    analysis = (active_cv.analysis or {}) if active_cv else {}
    email_row = None
    if active_cv and active_cv.email_id:
        email_row = db.session.get(TalentEmail, active_cv.email_id)
    if email_row is None:
        email_row = TalentEmail.query.filter_by(candidate_id=cand.id) \
            .order_by(TalentEmail.received_at.desc()).first()
    matches = TalentMatch.query.filter_by(candidate_id=cand.id).all()
    referrals = TalentReferral.query.filter_by(candidate_id=cand.id) \
        .order_by(TalentReferral.created_at.desc()).all()
    companies = {c.id: c for c in TalentCompany.query.all()}
    active_companies = sorted((c for c in companies.values() if c.active),
                              key=lambda c: c.name.lower())
    referred_company_ids = {r.company_id for r in referrals
                            if r.status != 'CANCELLED'}

    def fit_rank(m):
        return {'STRONG': 0, 'MAYBE': 1}.get(m.admin_fit or m.ai_fit, 2)
    matches.sort(key=fit_rank)

    # prev/next among the newest-first candidate list (J/K navigation)
    id_rows = db.session.query(TalentCandidate.id).filter(
        TalentCandidate.status != 'ARCHIVED') \
        .order_by(TalentCandidate.created_at.desc()).limit(1000).all()
    ids = [r[0] for r in id_rows]
    prev_id = next_id = None
    if cand.id in ids:
        i = ids.index(cand.id)
        prev_id = ids[i - 1] if i > 0 else None
        next_id = ids[i + 1] if i + 1 < len(ids) else None

    return render_template('admin/talent_candidate.html', cand=cand, cvs=cvs,
                           active_cv=active_cv, a=analysis, email_row=email_row,
                           gmail_link=_gmail_link(email_row.message_id) if email_row else '',
                           matches=matches, referrals=referrals,
                           companies=companies, active_companies=active_companies,
                           referred_company_ids=referred_company_ids,
                           prev_id=prev_id, next_id=next_id,
                           human_date=_human_date)


@admin_bp.route('/talent/companies')
@login_required
def talent_companies():
    comps = TalentCompany.query.order_by(TalentCompany.active.desc(),
                                         TalentCompany.name).all()
    match_counts = dict(db.session.query(
        TalentMatch.company_id, db.func.count(TalentMatch.id))
        .group_by(TalentMatch.company_id).all())
    ref_rows = db.session.query(
        TalentReferral.company_id, TalentReferral.status,
        db.func.count(TalentReferral.id)) \
        .group_by(TalentReferral.company_id, TalentReferral.status).all()
    ref_stats = {}
    for cid, status, n in ref_rows:
        ref_stats.setdefault(cid, {})[status] = n
    return render_template('admin/talent_companies.html', companies=comps,
                           match_counts=match_counts, ref_stats=ref_stats,
                           methods=REFERRAL_METHODS)


@admin_bp.route('/talent/company/<int:company_id>')
@login_required
def talent_company(company_id):
    comp = db.session.get(TalentCompany, company_id)
    if comp is None:
        return 'Company not found', 404
    matches = TalentMatch.query.filter_by(company_id=comp.id).all()
    refs = TalentReferral.query.filter_by(company_id=comp.id).all()
    cand_ids = list({m.candidate_id for m in matches}
                    | {r.candidate_id for r in refs})
    cands = {c.id: c for c in TalentCandidate.query.filter(
        TalentCandidate.id.in_(cand_ids)).all()} if cand_ids else {}
    refs_by_cand = _grouped(refs, lambda r: r.candidate_id)
    rows = []
    for m in matches:
        cand = cands.get(m.candidate_id)
        if cand is None:
            continue
        cand_refs = refs_by_cand.get(m.candidate_id, [])
        rows.append({'m': m, 'cand': cand,
                     'fit': m.admin_fit or m.ai_fit or '',
                     'ref_status': cand_refs[0].status if cand_refs else ''})
    rows.sort(key=lambda r: {'STRONG': 0, 'MAYBE': 1}.get(r['fit'], 2))
    stats = {
        'matched': len(matches),
        'referred': len(refs),
        'waiting': sum(1 for r in refs if r.status == 'WAITING'),
        'submitted': sum(1 for r in refs if r.status in ('SUBMITTED', 'COMPLETED')),
        'skipped': sum(1 for row in rows if row['cand'].status == 'SKIP'),
    }
    return render_template('admin/talent_company.html', comp=comp, rows=rows,
                           stats=stats, methods=REFERRAL_METHODS,
                           defaults={
                               'candidate_subject': tcfg.DEFAULT_CANDIDATE_EMAIL_SUBJECT,
                               'candidate_body': tcfg.DEFAULT_CANDIDATE_EMAIL_TEMPLATE,
                               'email_subject': tcfg.DEFAULT_REFERRAL_SUBJECT,
                               'email_body': tcfg.DEFAULT_REFERRAL_BODY,
                           })


@admin_bp.route('/talent/ai')
@login_required
def talent_ai():
    month = request.args.get('month') or datetime.utcnow().strftime('%Y-%m')
    try:
        start = datetime.strptime(month, '%Y-%m')
    except ValueError:
        start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
        month = start.strftime('%Y-%m')
    end = (start.replace(day=28) + timedelta(days=5)).replace(day=1)
    logs = TalentAiLog.query.filter(TalentAiLog.created_at >= start,
                                    TalentAiLog.created_at < end) \
        .order_by(TalentAiLog.created_at.desc()).all()
    cvs_analyzed = db.session.query(db.func.count(TalentCv.id)).filter(
        TalentCv.analyzed_at >= start, TalentCv.analyzed_at < end).scalar()

    from cv_review.gemini import PRICES_PER_1M
    by_model = {}
    for log in logs:
        m = by_model.setdefault(log.model or '?', {
            'calls': 0, 'input': 0, 'cached': 0, 'output': 0, 'errors': 0})
        m['calls'] += 1
        m['input'] += log.input_tokens or 0
        m['cached'] += log.cached_tokens or 0
        m['output'] += log.output_tokens or 0
        m['errors'] += 0 if log.ok else 1
    cost, priced = 0.0, True
    for model, m in by_model.items():
        prices = PRICES_PER_1M.get(model)
        if not prices:
            priced = False
            continue
        hit = min(m['cached'], m['input'])
        cost += ((m['input'] - hit) * prices[0] + hit * prices[2]
                 + m['output'] * prices[1]) / 1e6
    totals = {
        'cvs_analyzed': cvs_analyzed,
        'calls': len(logs),
        'input': sum(m['input'] for m in by_model.values()),
        'output': sum(m['output'] for m in by_model.values()),
        'cached': sum(m['cached'] for m in by_model.values()),
        'errors': sum(m['errors'] for m in by_model.values()),
        'cost': round(cost, 4) if (priced and by_model) else None,
    }
    return render_template('admin/talent_ai.html', month=month, totals=totals,
                           by_model=by_model, logs=logs[:50],
                           extraction_model=tcfg.extraction_model(),
                           matching_model=tcfg.matching_model(),
                           fallback_model=tcfg.fallback_model())


@admin_bp.route('/talent/cv/<cv_id>/file')
@login_required
def talent_cv_file(cv_id):
    cv = db.session.get(TalentCv, cv_id)
    if cv is None or not cv.file:
        return 'CV not found', 404
    if cv.ext == '.pdf':
        mime, disposition = 'application/pdf', 'inline'
    else:
        mime = ('application/vnd.openxmlformats-officedocument'
                '.wordprocessingml.document')
        disposition = 'attachment'
    safe_name = re.sub(r'[^\w.\- ]', '_', cv.filename or f'cv{cv.ext}')
    return Response(cv.file, mimetype=mime, headers={
        'Content-Disposition': f'{disposition}; filename="{safe_name}"',
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'private, no-store',
    })


# ---------------------------------------------------------------------------
# API — sync + candidates
# ---------------------------------------------------------------------------

def _cron_authorized():
    """Same keyed-endpoint pattern as /wa/backfill-cron: ?key= or X-Admin-Key
    matching ADMIN_SECRET, fail-closed when the secret is unset."""
    secret = os.environ.get('ADMIN_SECRET')
    supplied = request.headers.get('X-Admin-Key') or request.args.get('key')
    return bool(secret) and supplied == secret


@admin_bp.route('/api/talent/sync', methods=['POST'])
def talent_sync():
    """Ingest new CV emails. Callable from the dashboard (admin session) or
    from a cron/scheduled routine (admin key) — analysis runs in background
    either way, so the call returns in seconds."""
    if not (session.get('admin_logged_in') or _cron_authorized()):
        return _err('forbidden', 403)
    summary = sync_gmail()
    if summary.get('ok'):
        analyze_pending_async(current_app._get_current_object())
    return jsonify(summary), (200 if summary.get('ok') else 400)


@admin_bp.route('/api/talent/candidates', methods=['POST'])
@login_required
def talent_create_candidate():
    file = request.files.get('file')
    if file is None:
        return _err('A CV file (PDF/DOCX) is required.')
    file_bytes = file.read()
    email = (request.form.get('email') or '').strip()[:256]
    name = (request.form.get('name') or '').strip()[:256]
    source = (request.form.get('source') or 'MANUAL').strip()[:64]
    notes = (request.form.get('notes') or '').strip()[:4000]
    cand, created = ensure_candidate(email=email, name=name, source=source)
    if created and notes:
        cand.notes = notes
    if not created and name and not cand.name:
        cand.name = name
    try:
        add_cv(cand, file_bytes, file.filename)
    except UploadError as exc:
        db.session.rollback()
        return _err(str(exc))
    analyze_pending_async(current_app._get_current_object())
    return jsonify({'ok': True, 'id': cand.id, 'existing': not created})


@admin_bp.route('/api/talent/candidate/<cand_id>/cv', methods=['POST'])
@login_required
def talent_upload_cv(cand_id):
    cand = db.session.get(TalentCandidate, cand_id)
    if cand is None:
        return _err('Candidate not found', 404)
    file = request.files.get('file')
    if file is None:
        return _err('A CV file (PDF/DOCX) is required.')
    try:
        cv = add_cv(cand, file.read(), file.filename)
    except UploadError as exc:
        db.session.rollback()
        return _err(str(exc))
    analyze_pending_async(current_app._get_current_object())
    return jsonify({'ok': True, 'version': cv.version})


@admin_bp.route('/api/talent/candidate/<cand_id>', methods=['PUT'])
@login_required
def talent_update_candidate(cand_id):
    cand = db.session.get(TalentCandidate, cand_id)
    if cand is None:
        return _err('Candidate not found', 404)
    data = request.get_json(silent=True) or {}
    caps = {'name': 256, 'email': 256, 'phone': 64, 'city': 128,
            'current_title': 256, 'source': 64, 'notes': 8000}
    for field, cap in caps.items():
        if field in data:
            value = (str(data[field] or '').strip() or None)
            setattr(cand, field, value[:cap] if value else None)
    if 'seniority' in data:
        s = (data['seniority'] or '').upper()
        cand.seniority = s if s in ('JUNIOR', 'MID', 'SENIOR', 'STAFF') else None
    if 'years_experience' in data:
        try:
            cand.years_experience = (round(float(data['years_experience']), 1)
                                     if data['years_experience'] not in (None, '')
                                     else None)
        except (TypeError, ValueError):
            pass
    if 'status' in data:
        status = (data['status'] or '').upper()
        if status not in CANDIDATE_STATUSES:
            return _err(f'Invalid status {status!r}')
        cand.status = status
    db.session.commit()
    return jsonify({'ok': True})


@admin_bp.route('/api/talent/candidate/<cand_id>/analyze', methods=['POST'])
@login_required
def talent_reanalyze(cand_id):
    cand = db.session.get(TalentCandidate, cand_id)
    if cand is None:
        return _err('Candidate not found', 404)
    cv = TalentCv.query.options(*_CV_META).filter_by(
        candidate_id=cand.id, is_active=True).first()
    if cv is None:
        return _err('Candidate has no CV to analyze.')
    cv.analysis_status = 'pending'
    cv.analysis_error = None
    db.session.commit()
    analyze_pending_async(current_app._get_current_object())
    return jsonify({'ok': True})


@admin_bp.route('/api/talent/candidate/<cand_id>/analysis-status')
@login_required
def talent_analysis_status(cand_id):
    cv = TalentCv.query.options(*_CV_META).filter_by(
        candidate_id=cand_id, is_active=True).first()
    if cv is None:
        return jsonify({'status': 'none'})
    return jsonify({'status': cv.analysis_status, 'error': cv.analysis_error})


@admin_bp.route('/api/talent/candidate/<cand_id>/companies', methods=['POST'])
@login_required
def talent_add_company_match(cand_id):
    """Manual company add (§9) — works even when AI said NO_MATCH or never
    evaluated this pairing."""
    cand = db.session.get(TalentCandidate, cand_id)
    data = request.get_json(silent=True) or {}
    comp = db.session.get(TalentCompany, data.get('company_id') or 0)
    if cand is None or comp is None:
        return _err('Candidate or company not found', 404)
    match = TalentMatch.query.filter_by(candidate_id=cand.id,
                                        company_id=comp.id).first()
    if match is None:
        match = TalentMatch(candidate_id=cand.id, company_id=comp.id,
                            source='MANUAL')
        db.session.add(match)
    fit = (data.get('fit') or 'MAYBE').upper()
    match.admin_fit = fit if fit in FIT_LEVELS else 'MAYBE'
    match.overridden = True
    db.session.commit()
    return jsonify({'ok': True, 'match_id': match.id})


@admin_bp.route('/api/talent/match/<int:match_id>/override', methods=['POST'])
@login_required
def talent_override_match(match_id):
    match = db.session.get(TalentMatch, match_id)
    if match is None:
        return _err('Match not found', 404)
    fit = ((request.get_json(silent=True) or {}).get('fit') or '').upper()
    if fit == 'CLEAR':
        match.admin_fit = None
        match.overridden = False
    elif fit in FIT_LEVELS:
        match.admin_fit = fit
        match.overridden = True
    else:
        return _err(f'Invalid fit {fit!r}')
    db.session.commit()
    return jsonify({'ok': True})


@admin_bp.route('/api/talent/bulk', methods=['POST'])
@login_required
def talent_bulk():
    """Safe bulk ops only (§28): status changes + add-company. No bulk sends."""
    data = request.get_json(silent=True) or {}
    ids = [str(i)[:36] for i in (data.get('ids') or [])][:200]
    action = (data.get('action') or '').lower()
    if not ids:
        return _err('No candidates selected.')
    cands = TalentCandidate.query.filter(TalentCandidate.id.in_(ids)).all()
    status_map = {'strong': 'STRONG', 'maybe': 'MAYBE', 'skip': 'SKIP',
                  'archive': 'ARCHIVED', 'new': 'NEW', 'completed': 'COMPLETED'}
    if action in status_map:
        for c in cands:
            c.status = status_map[action]
    elif action == 'add_company':
        comp = db.session.get(TalentCompany, data.get('company_id') or 0)
        if comp is None:
            return _err('Company not found', 404)
        existing = {m.candidate_id for m in TalentMatch.query.filter(
            TalentMatch.candidate_id.in_(ids),
            TalentMatch.company_id == comp.id).all()}
        for c in cands:
            if c.id in existing:
                continue
            db.session.add(TalentMatch(candidate_id=c.id, company_id=comp.id,
                                       source='MANUAL', admin_fit='MAYBE',
                                       overridden=True))
    else:
        return _err(f'Unknown bulk action {action!r}')
    db.session.commit()
    return jsonify({'ok': True, 'count': len(cands)})


def _claude_handoff_prompt(cand, comp, cv):
    """A ready-to-paste prompt for a Claude-in-Chrome session that performs the
    manual portal submission (e.g. Zafran's Ashby). Contains only stored data."""
    base = request.host_url.rstrip('/')
    cv_line = (f'{base}/admin/talent/cv/{cv.id}/file' if cv
               else '(no CV on file — ask me for one)')
    instructions = (comp.portal_instructions.strip() if comp.portal_instructions
                    else "Use the portal's referral/candidate-add flow "
                         "(e.g. in Ashby: + Add -> Referral, pick the matching "
                         "open job).")
    return (
        f'Submit a referral for this candidate in {comp.name}\'s application '
        f'portal using Claude in Chrome (I am logged in to both the portal and '
        f'my admin).\n'
        f'\n'
        f'Candidate details (use EXACTLY these, ask me if a required field is '
        f'missing — never invent data):\n'
        f'- Name: {cand.name or "?"}\n'
        f'- Email: {cand.email or "?"}\n'
        f'- Phone: {cand.phone or "?"}\n'
        f'- Role: {cand.current_title or "?"}\n'
        f'- City: {cand.city or "?"}\n'
        f'\n'
        f'Steps:\n'
        f'1. Open {cv_line} in the browser and download the CV file.\n'
        f'2. Open the portal: {comp.portal_url or "(portal URL not configured — ask me)"}\n'
        f'3. {instructions}\n'
        f'4. Fill in the candidate details, attach the downloaded CV, and STOP '
        f'before the final submit so I can confirm.\n'
        f'5. After I confirm and it is submitted, mark the referral as Uploaded '
        f'here: {base}/admin/talent/candidate/{cand.id}\n'
    )


@admin_bp.route('/api/talent/candidate/<cand_id>/quick-refer', methods=['POST'])
@login_required
def talent_quick_refer(cand_id):
    """ONE pre-configured action button per company:
      REFERRAL_LINK  -> sends the templated link email to the candidate NOW
      EMAIL          -> creates/reuses the referral, returns ref_id so the UI
                        opens the prefilled compose modal (one click to send)
      MANUAL_UPLOAD  -> creates/reuses the referral, returns the handoff pack
                        (portal URL, copyable details, Claude-in-Chrome prompt)
    Duplicate guard: a referral to this company that already progressed past
    NEEDS_ACTION returns 409 unless force=true."""
    cand = db.session.get(TalentCandidate, cand_id)
    data = request.get_json(silent=True) or {}
    comp = db.session.get(TalentCompany, data.get('company_id') or 0)
    if cand is None or comp is None:
        return _err('Candidate or company not found', 404)

    existing = TalentReferral.query.filter(
        TalentReferral.candidate_id == cand.id,
        TalentReferral.company_id == comp.id,
        TalentReferral.status != 'CANCELLED') \
        .order_by(TalentReferral.created_at.desc()).first()
    if existing and existing.status != 'NEEDS_ACTION' and not data.get('force'):
        return jsonify({
            'error': (f'{cand.name or "This candidate"} was already referred to '
                      f'{comp.name} on {existing.created_at.strftime("%b %-d")} '
                      f'(status: {existing.status}). Do it again anyway?'),
            'duplicate': True}), 409

    active_cv = TalentCv.query.options(*_CV_META).filter_by(
        candidate_id=cand.id, is_active=True).first()
    if existing and existing.status == 'NEEDS_ACTION':
        ref = existing
        if ref.method != comp.referral_method:
            # Untouched referral + company method changed since: refresh the
            # snapshot so the action matches today's configuration.
            ref.add_event('method_updated',
                          f'{ref.method} -> {comp.referral_method}')
            ref.method = comp.referral_method
    else:
        ref = TalentReferral(candidate_id=cand.id, company_id=comp.id,
                             cv_id=active_cv.id if active_cv else None,
                             method=comp.referral_method)
        ref.add_event('created', f'quick action, method {comp.referral_method}')
        db.session.add(ref)
        db.session.flush()

    if ref.method == 'REFERRAL_LINK':
        preview = temails.candidate_link_email(cand, comp)
        if preview['warnings']:
            db.session.commit()  # keep the referral pending in Needs Action
            return _err(' '.join(preview['warnings']))
        ok, err = temails.send_email(cand.email, preview['subject'],
                                     preview['body'])
        if not ok:
            db.session.commit()
            return _err(err)
        ref.status = 'WAITING'
        ref.add_event('link_email_sent', f'to {cand.email} (quick action)')
        db.session.commit()
        return jsonify({'ok': True, 'action': 'link_sent', 'to': cand.email,
                        'company': comp.name})

    if ref.method == 'EMAIL':
        db.session.commit()
        return jsonify({'ok': True, 'action': 'email_preview', 'ref_id': ref.id})

    # MANUAL_UPLOAD — hand everything needed to finish in the portal fast
    db.session.commit()
    a = (active_cv.analysis or {}) if active_cv else {}
    details = '\n'.join(filter(None, [
        f'Name: {cand.name or ""}',
        f'Email: {cand.email or ""}',
        f'Phone: {cand.phone or ""}',
        f'Role: {cand.current_title or ""}',
        f'Summary: {a.get("summary") or ""}',
    ]))
    return jsonify({'ok': True, 'action': 'manual', 'ref_id': ref.id,
                    'company': comp.name,
                    'portal_url': comp.portal_url or '',
                    'instructions': comp.portal_instructions or '',
                    'details': details,
                    'claude_prompt': _claude_handoff_prompt(cand, comp, active_cv)})


# ---------------------------------------------------------------------------
# API — referrals
# ---------------------------------------------------------------------------

@admin_bp.route('/api/talent/referrals', methods=['POST'])
@login_required
def talent_create_referral():
    data = request.get_json(silent=True) or {}
    cand = db.session.get(TalentCandidate, str(data.get('candidate_id') or ''))
    comp = db.session.get(TalentCompany, data.get('company_id') or 0)
    if cand is None or comp is None:
        return _err('Candidate or company not found', 404)
    # §31: warn about double referrals; proceed only with an explicit force.
    existing = TalentReferral.query.filter(
        TalentReferral.candidate_id == cand.id,
        TalentReferral.company_id == comp.id,
        TalentReferral.status != 'CANCELLED').first()
    if existing and not data.get('force'):
        return jsonify({
            'error': (f'{cand.name or "This candidate"} was already referred to '
                      f'{comp.name} on {existing.created_at.strftime("%b %-d")} '
                      f'(status: {existing.status}).'),
            'duplicate': True}), 409
    active_cv = TalentCv.query.options(*_CV_META).filter_by(
        candidate_id=cand.id, is_active=True).first()
    ref = TalentReferral(candidate_id=cand.id, company_id=comp.id,
                         cv_id=active_cv.id if active_cv else None,
                         method=comp.referral_method)
    ref.add_event('created', f'method {comp.referral_method}')
    db.session.add(ref)
    db.session.commit()
    return jsonify({'ok': True, 'id': ref.id, 'method': ref.method})


@admin_bp.route('/api/talent/referral/<int:ref_id>/email-preview')
@login_required
def talent_referral_preview(ref_id):
    ref = db.session.get(TalentReferral, ref_id)
    if ref is None:
        return _err('Referral not found', 404)
    cand = db.session.get(TalentCandidate, ref.candidate_id)
    comp = db.session.get(TalentCompany, ref.company_id)
    cv = TalentCv.query.options(*_CV_META).filter_by(id=ref.cv_id).first() \
        if ref.cv_id else None
    analysis = (cv.analysis or {}) if cv else {}
    if ref.method == 'REFERRAL_LINK':
        preview = temails.candidate_link_email(cand, comp)
    elif ref.method == 'EMAIL':
        preview = temails.company_referral_email(cand, comp, analysis)
        if cv is None:
            preview['warnings'].append('No CV on file to attach.')
    else:
        return _err('This referral method has no email step.')
    preview['method'] = ref.method
    return jsonify(preview)


@admin_bp.route('/api/talent/referral/<int:ref_id>/send-email', methods=['POST'])
@login_required
def talent_referral_send(ref_id):
    """The ONLY place outbound referral email happens — after the admin saw the
    preview and clicked send. Subject/body may be edited in the preview modal;
    recipients always come from stored config (§14)."""
    ref = db.session.get(TalentReferral, ref_id)
    if ref is None:
        return _err('Referral not found', 404)
    cand = db.session.get(TalentCandidate, ref.candidate_id)
    comp = db.session.get(TalentCompany, ref.company_id)
    data = request.get_json(silent=True) or {}
    subject = (data.get('subject') or '').strip()[:500]
    body = (data.get('body') or '').strip()[:20000]
    if not subject or not body:
        return _err('Subject and body are required.')

    if ref.method == 'REFERRAL_LINK':
        if not cand.email:
            return _err('Candidate has no email address.')
        ok, err = temails.send_email(cand.email, subject, body)
        if not ok:
            return _err(err)
        ref.status = 'WAITING'
        ref.add_event('link_email_sent', f'to {cand.email}')
    elif ref.method == 'EMAIL':
        if not comp.email_to:
            return _err('Company has no referral recipient configured.')
        attachment = None
        if ref.cv_id:
            cv = db.session.get(TalentCv, ref.cv_id)
            if cv and cv.file:
                attachment = (cv.filename or f'cv{cv.ext}', cv.file)
        ok, err = temails.send_email(comp.email_to, subject, body,
                                     cc=comp.email_cc, attachment=attachment)
        if not ok:
            return _err(err)
        ref.status = 'SUBMITTED'
        ref.add_event('referral_email_sent',
                      f'to {comp.email_to}' + (' (CV attached)' if attachment else ''))
    else:
        return _err('This referral method has no email step.')
    db.session.commit()
    return jsonify({'ok': True, 'status': ref.status})


@admin_bp.route('/api/talent/referral/<int:ref_id>/status', methods=['POST'])
@login_required
def talent_referral_status(ref_id):
    ref = db.session.get(TalentReferral, ref_id)
    if ref is None:
        return _err('Referral not found', 404)
    data = request.get_json(silent=True) or {}
    status = (data.get('status') or '').upper()
    if status not in REFERRAL_STATUSES:
        return _err(f'Invalid status {status!r}')
    ref.status = status
    ref.add_event(f'status:{status}', (data.get('detail') or '')[:500])
    if 'note' in data:
        ref.note = (data.get('note') or '').strip()[:4000] or None
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# API — companies
# ---------------------------------------------------------------------------

def _apply_company_payload(comp, data):
    for field, cap in (('name', 256), ('referral_url', 2000),
                       ('candidate_email_subject', 500),
                       ('candidate_email_template', 8000),
                       ('portal_url', 2000), ('portal_instructions', 8000),
                       ('email_to', 256), ('email_cc', 256),
                       ('email_subject_template', 500),
                       ('email_body_template', 8000),
                       ('hiring_notes', 8000), ('internal_notes', 8000)):
        if field in data:
            value = (str(data[field] or '').strip() or None)
            setattr(comp, field, value[:cap] if value else None)
    if 'referral_method' in data:
        method = (data['referral_method'] or '').upper()
        if method not in REFERRAL_METHODS:
            raise ValueError(f'Invalid referral method {method!r}')
        comp.referral_method = method
    if 'active' in data:
        comp.active = bool(data['active'])
    for field in ('target_roles', 'required_skills', 'preferred_skills',
                  'locations'):
        if field in data:
            setattr(comp, field, _parse_list(data[field]) or None)
    if 'target_seniority' in data:
        wanted = [s.upper() for s in _parse_list(data['target_seniority'])
                  if s.upper() in ('JUNIOR', 'MID', 'SENIOR', 'STAFF')]
        comp.target_seniority = wanted or None
    if 'min_years' in data:
        try:
            comp.min_years = (float(data['min_years'])
                              if data['min_years'] not in (None, '') else None)
        except (TypeError, ValueError):
            comp.min_years = None


@admin_bp.route('/api/talent/companies', methods=['POST'])
@login_required
def talent_create_company():
    data = request.get_json(silent=True) or {}
    if not (data.get('name') or '').strip():
        return _err('Company name is required.')
    if (data.get('referral_method') or '').upper() not in REFERRAL_METHODS:
        return _err('Pick a referral method.')
    comp = TalentCompany(name='pending', referral_method='EMAIL')
    try:
        _apply_company_payload(comp, data)
    except ValueError as exc:
        return _err(str(exc))
    db.session.add(comp)
    db.session.commit()
    return jsonify({'ok': True, 'id': comp.id})


@admin_bp.route('/api/talent/company/<int:company_id>', methods=['PUT'])
@login_required
def talent_update_company(company_id):
    comp = db.session.get(TalentCompany, company_id)
    if comp is None:
        return _err('Company not found', 404)
    data = request.get_json(silent=True) or {}
    try:
        _apply_company_payload(comp, data)
    except ValueError as exc:
        return _err(str(exc))
    if not comp.name:
        return _err('Company name is required.')
    db.session.commit()
    return jsonify({'ok': True})


@admin_bp.route('/api/talent/company/<int:company_id>/find-candidates',
                methods=['POST'])
@login_required
def talent_find_candidates(company_id):
    """§37: deterministic shortlist from STORED analyses — zero AI cost. The
    admin then explicitly chooses to run one AI call on the shortlist."""
    comp = db.session.get(TalentCompany, company_id)
    if comp is None:
        return _err('Company not found', 404)
    cands = TalentCandidate.query.filter(
        TalentCandidate.status.notin_(('SKIP', 'ARCHIVED'))).limit(1000).all()
    cvs = _active_cvs([c.id for c in cands])
    referred = {r.candidate_id for r in TalentReferral.query.filter_by(
        company_id=comp.id).all()}
    scored = []
    for cand in cands:
        cv = cvs.get(cand.id)
        analysis = (cv.analysis or {}) if cv else None
        if not analysis or cv.analysis_status != 'complete':
            continue
        ok, score = plausible(analysis, comp)
        if ok:
            scored.append((score, cand, analysis))
    scored.sort(key=lambda t: -t[0])
    top = scored[:25]
    return jsonify({
        'possible': len(scored),
        'candidates': [{
            'id': cand.id, 'name': cand.name or cand.email or 'Unknown',
            'role': analysis.get('current_title') or '',
            'years': analysis.get('years_experience'),
            'score': score,
            'already_referred': cand.id in referred,
        } for score, cand, analysis in top],
    })


@admin_bp.route('/api/talent/company/<int:company_id>/analyze-candidates',
                methods=['POST'])
@login_required
def talent_analyze_candidates(company_id):
    comp = db.session.get(TalentCompany, company_id)
    if comp is None:
        return _err('Company not found', 404)
    ids = [str(i)[:36] for i in
           ((request.get_json(silent=True) or {}).get('candidate_ids') or [])][:25]
    if not ids:
        return _err('No candidates selected.')
    cands = TalentCandidate.query.filter(TalentCandidate.id.in_(ids)).all()
    cvs = _active_cvs([c.id for c in cands])
    pairs = [(c, cvs[c.id].analysis) for c in cands
             if c.id in cvs and cvs[c.id].analysis]
    if not pairs:
        return _err('Selected candidates have no completed analyses.')
    from cv_review.gemini import GeminiError
    try:
        updated = run_reverse_matching(comp, pairs)
    except GeminiError as exc:
        return _err(f'AI matching failed: {exc}', 502)
    return jsonify({'ok': True, 'updated': len(updated)})
