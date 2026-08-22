"""Candidate <-> company matching.

Cost discipline (§25, §37): a cheap deterministic prefilter picks plausible
companies from the stored structured extraction; ONE Gemini call then judges
the whole shortlist together. Never one API request per company. The reverse
direction (new company -> existing candidates) works the same way.
"""
from datetime import datetime

from cv_review.gemini import UsageTracker
from database.models import db

from . import config
from .extract import _call_with_fallback
from .models import TalentMatch

SHORTLIST_CAP = 15

_STR = {'type': 'string'}
_STR_ARR = {'type': 'array', 'items': _STR}

MATCH_SCHEMA = {
    'type': 'object',
    'properties': {
        'matches': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {
                'company_id': {'type': 'integer'},
                'candidate_id': _STR,
                'fit': {'type': 'string', 'enum': ['STRONG', 'MAYBE', 'NO_MATCH']},
                'pros': _STR_ARR,
                'cons': _STR_ARR,
            },
            'required': ['fit', 'pros', 'cons'],
        }},
    },
    'required': ['matches'],
}

MATCH_PROMPT = """You match tech candidates to companies for a referral service.
For EACH pairing below, judge the fit from the candidate profile against the company's target profile and hiring notes.

Rules:
- fit: STRONG = clearly worth referring, MAYBE = partial fit, NO_MATCH = don't refer.
- pros: max 4 short bullets — concrete reasons the candidate fits (met requirements).
- cons: max 3 short bullets — real gaps only (e.g. "Go not mentioned"). Empty array if none. Never invent filler.
- A company with little/no target profile: judge general fit for a tech company of that kind.
- Echo back company_id (and candidate_id when given) exactly.
- Be decisive and concise; bullets under 10 words.
"""


def _tokens(*values):
    """Lowercased word set from strings/lists, for fuzzy overlap tests."""
    out = set()
    for v in values:
        items = v if isinstance(v, (list, tuple)) else [v]
        for item in items:
            for w in str(item or '').lower().replace('/', ' ').split():
                w = w.strip('.,()')
                if len(w) > 1:
                    out.add(w)
    return out


def _roles_overlap(analysis, company):
    targets = company.target_roles or []
    if not targets:
        return True
    cand = _tokens(analysis.get('roles'), analysis.get('current_title'))
    # Generic words shared by most role names don't establish an overlap.
    cand -= {'engineer', 'developer', 'senior', 'junior', 'lead', 'staff'}
    for role in targets:
        t = _tokens(role) - {'engineer', 'developer', 'senior', 'junior', 'lead', 'staff'}
        if not t or (t & cand):
            return True
    return False


def plausible(analysis, company):
    """Deterministic prefilter — recall-oriented: only HARD constraint failures
    exclude a company; Gemini refines the survivors. Returns (ok, score)."""
    if not analysis:
        return False, 0
    # Hard constraints
    years = analysis.get('years_experience')
    if company.min_years and years is not None and years < company.min_years - 1:
        return False, 0
    if not _roles_overlap(analysis, company):
        return False, 0
    sen = analysis.get('seniority')
    targets_sen = [s.upper() for s in (company.target_seniority or [])]
    if targets_sen and sen and sen.upper() not in targets_sen:
        return False, 0
    # Soft score for shortlist ordering
    skills = _tokens(analysis.get('skills'))
    score = 1
    score += len(_tokens(company.required_skills) & skills) * 2
    score += len(_tokens(company.preferred_skills) & skills)
    if company.min_years and years is not None and years >= company.min_years:
        score += 1
    return True, score


def shortlist_companies(analysis, companies):
    """Plausible active companies, best-first, capped."""
    scored = []
    for c in companies:
        ok, score = plausible(analysis, c)
        if ok:
            scored.append((score, c))
    scored.sort(key=lambda t: -t[0])
    return [c for _, c in scored[:SHORTLIST_CAP]]


def _candidate_profile(candidate, analysis):
    a = analysis or {}
    return {
        'candidate_id': candidate.id,
        'title': a.get('current_title') or candidate.current_title,
        'seniority': a.get('seniority') or candidate.seniority,
        'years_experience': a.get('years_experience', candidate.years_experience),
        'roles': a.get('roles', []),
        'skills': a.get('skills', []),
        'summary': a.get('summary', ''),
    }


def _company_profile(company):
    return {
        'company_id': company.id,
        'name': company.name,
        'target_roles': company.target_roles or [],
        'target_seniority': company.target_seniority or [],
        'required_skills': company.required_skills or [],
        'preferred_skills': company.preferred_skills or [],
        'min_years_experience': company.min_years,
        'locations': company.locations or [],
        'hiring_notes': (company.hiring_notes or '')[:1500],
    }


def _upsert_match(candidate_id, company_id, verdict, model, existing_by_company):
    """Write AI fields; NEVER touch admin_fit/overridden (§9)."""
    row = existing_by_company.get(company_id)
    if row is None:
        row = TalentMatch(candidate_id=candidate_id, company_id=company_id, source='AI')
        db.session.add(row)
        existing_by_company[company_id] = row
    row.ai_fit = verdict.get('fit')
    row.ai_pros = (verdict.get('pros') or [])[:5]
    row.ai_cons = (verdict.get('cons') or [])[:4]
    row.model = model
    row.matched_at = datetime.utcnow()


def run_matching(candidate, analysis, companies):
    """Candidate -> companies: prefilter, then ONE Gemini call for the whole
    shortlist. Upserts talent_matches; admin overrides survive untouched."""
    import json as _json
    short = shortlist_companies(analysis, [c for c in companies if c.active])
    existing = {m.company_id: m for m in TalentMatch.query.filter_by(
        candidate_id=candidate.id).all()}
    if not short:
        return []

    tracker = UsageTracker()
    parts = [{'text': MATCH_PROMPT},
             {'text': 'CANDIDATE:\n' + _json.dumps(_candidate_profile(candidate, analysis),
                                                   ensure_ascii=False)},
             {'text': 'COMPANIES:\n' + _json.dumps([_company_profile(c) for c in short],
                                                   ensure_ascii=False)}]
    data = _call_with_fallback(parts, MATCH_SCHEMA, purpose='talent_match',
                               tracker=tracker, model=config.matching_model(),
                               kind='match', candidate_id=candidate.id)
    model = tracker.calls[-1]['model'] if tracker.calls else config.matching_model()
    valid_ids = {c.id for c in short}
    for verdict in data.get('matches', []):
        cid = verdict.get('company_id')
        if cid in valid_ids:
            _upsert_match(candidate.id, cid, verdict, model, existing)
    db.session.commit()
    return [existing[c.id] for c in short if c.id in existing]


def run_reverse_matching(company, candidates_with_analysis):
    """New/edited company -> existing candidates (§37): ONE Gemini call judging
    the already-shortlisted candidates against this single company."""
    import json as _json
    if not candidates_with_analysis:
        return []
    tracker = UsageTracker()
    profiles = [_candidate_profile(cand, analysis)
                for cand, analysis in candidates_with_analysis]
    parts = [{'text': MATCH_PROMPT},
             {'text': 'COMPANY:\n' + _json.dumps(_company_profile(company),
                                                 ensure_ascii=False)},
             {'text': 'CANDIDATES:\n' + _json.dumps(profiles, ensure_ascii=False)}]
    data = _call_with_fallback(parts, MATCH_SCHEMA, purpose='talent_match_reverse',
                               tracker=tracker, model=config.matching_model(),
                               kind='match', candidate_id=None)
    model = tracker.calls[-1]['model'] if tracker.calls else config.matching_model()

    by_candidate = {cand.id: cand for cand, _ in candidates_with_analysis}
    cand_ids = list(by_candidate)
    existing_rows = TalentMatch.query.filter(
        TalentMatch.candidate_id.in_(cand_ids),
        TalentMatch.company_id == company.id).all()
    updated = []
    for verdict in data.get('matches', []):
        cid = verdict.get('candidate_id')
        if cid not in by_candidate:
            continue
        existing = {r.company_id: r for r in existing_rows if r.candidate_id == cid}
        _upsert_match(cid, company.id, verdict, model, existing)
        updated.append(cid)
    db.session.commit()
    return updated
