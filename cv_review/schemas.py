"""Response schemas for the Gemini structured-output calls, plus our own
strict server-side validation of what comes back (never trust model output
shape, even with responseSchema)."""

# The 10 product rules — the same Hebrew rule names the V1 reviewer shipped
# with; they are the "CV Rules X/10" score and the guide checklist in the UI.
RULES = [
    'עמוד אחד',
    'באנגלית',
    'בלי תמונה ופרטים מיותרים',
    'טייטל מתחת לשם',
    'פסקת פתיחה',
    'טכנולוגיות מודגשות',
    'פעלים חזקים ומספרים',
    'רשימת כישורים כנה',
    'פרויקטים ו-GitHub',
    'AI משולב נכון',
]

CHANGE_TYPES = ['keep', 'rewrite', 'remove', 'reorder', 'shorten',
                'location_redaction', 'keyword_surface', 'formatting',
                'deduplication']

_STR = {'type': 'string'}
_NSTR = {'type': 'string', 'nullable': True}
_STR_ARR = {'type': 'array', 'items': _STR}


def _obj(props, required=None):
    o = {'type': 'object', 'properties': props}
    if required:
        o['required'] = required
    return o


def _arr(items):
    return {'type': 'array', 'items': items}


# ── Extraction: untrusted document → canonical structured CV + evidence ─────
EXTRACTION_SCHEMA = _obj({
    'is_cv': {'type': 'boolean'},
    'candidate_name': _obj({
        'full_name': _NSTR,
        'confidence': {'type': 'number'},
        'source_text': _STR,
    }, ['confidence']),
    'contact': _obj({
        'email': _NSTR, 'phone': _NSTR,
        'location_raw': _NSTR, 'city': _NSTR, 'country': _NSTR,
        'links': _arr(_obj({'label': _STR, 'url': _STR})),
    }),
    'title': _NSTR,
    'summary': _NSTR,
    'skills': _arr(_obj({'name': _STR, 'source_text': _STR}, ['name'])),
    'experience': _arr(_obj({
        'company': _STR, 'title': _STR, 'dates': _STR, 'bullets': _STR_ARR,
    })),
    'projects': _arr(_obj({'name': _STR, 'description': _STR, 'link': _NSTR})),
    'education': _arr(_obj({'institution': _STR, 'degree': _STR, 'dates': _STR})),
    'extras': _arr(_obj({'heading': _STR, 'lines': _STR_ARR})),
    'flags': _obj({
        'has_photo': {'type': 'boolean'},
        'language': {'type': 'string', 'enum': ['en', 'he', 'mixed', 'other']},
        'self_ratings': {'type': 'boolean'},
        'emphasized_technologies': {'type': 'boolean'},
        'page_count_estimate': {'type': 'number'},
    }),
}, ['is_cv', 'candidate_name', 'contact', 'flags'])


# ── Critic: canonical CV (+ optional JD) → rules checklist + scores ─────────
CRITIC_SCHEMA = _obj({
    'rules_checklist': _arr(_obj({
        'rule': {'type': 'string', 'enum': RULES},
        'status': {'type': 'string', 'enum': ['pass', 'partial', 'fail']},
        'note': _STR,
    }, ['rule', 'status'])),
    'quality_score': {'type': 'integer'},
    'jd_match': {'type': 'integer', 'nullable': True},
    'verdict': _STR,
    'strengths': _STR_ARR,
    'improvements': _arr(_obj({
        'area': _STR, 'issue': _STR, 'fix': _STR,
        'before': _STR, 'rewrite': _STR,
    })),
    'action_items': _STR_ARR,
}, ['rules_checklist', 'quality_score', 'verdict'])


# ── Optimizer: canonical CV + job input → optimized CV + change ledger ──────
_OPTIMIZED_CV = _obj({
    'name': _STR,
    'title': _STR,
    'location': _NSTR,                    # city-level max; may be omitted
    'email': _NSTR, 'phone': _NSTR,
    'links': _arr(_obj({'label': _STR, 'url': _STR})),
    'summary': _STR,
    'skills_groups': _arr(_obj({'group': _STR, 'skills': _STR_ARR}, ['group', 'skills'])),
    'experience': _arr(_obj({
        'company': _STR, 'title': _STR, 'dates': _STR, 'bullets': _STR_ARR,
    }, ['company', 'title', 'bullets'])),
    'projects': _arr(_obj({'name': _STR, 'tech': _NSTR, 'description': _STR, 'link': _NSTR}, ['name'])),
    'education': _arr(_obj({'institution': _STR, 'degree': _STR, 'dates': _STR})),
    'extras': _arr(_obj({'heading': _STR, 'lines': _STR_ARR})),
}, ['name', 'title', 'summary'])

OPTIMIZER_SCHEMA = _obj({
    'optimized_cv': _OPTIMIZED_CV,
    'changes': _arr(_obj({
        'change_type': {'type': 'string', 'enum': CHANGE_TYPES},
        'section': _STR,
        'before': _STR,
        'after': _STR,
        'reason': _STR,
        'evidence_refs': _STR_ARR,
    }, ['change_type', 'section', 'reason'])),
    'jd_analysis': {
        'type': 'object', 'nullable': True,
        'properties': {
            'strong_matches': _STR_ARR,
            'surfaced': _STR_ARR,
            'not_evidenced': _STR_ARR,
        },
    },
    'career_recommendations': _arr(_obj({
        'skill': _STR,
        'priority': {'type': 'string', 'enum': ['high', 'medium', 'low']},
        'reason_type': {'type': 'string',
                        'enum': ['target_job_gap', 'role_framework_gap', 'cv_information_gap']},
        'reason': _STR,
        'cv_evidence': {'type': 'string', 'enum': ['found', 'partial', 'not_found']},
        'recommendation': _STR,
        'cv_instruction': _STR,
    }, ['skill', 'priority', 'reason_type', 'reason', 'cv_evidence', 'recommendation'])),
}, ['optimized_cv', 'changes', 'career_recommendations'])


TRANSLATION_SCHEMA = _obj({'lines': _STR_ARR}, ['lines'])


# ── Server-side structural validation ────────────────────────────────────────
class SchemaError(ValueError):
    pass


def _strip_nul(obj):
    """Postgres JSON columns reject \\u0000 in strings — model output extracted
    from arbitrary PDFs can contain them. Scrub recursively."""
    if isinstance(obj, str):
        return obj.replace('\x00', '')
    if isinstance(obj, list):
        return [_strip_nul(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _strip_nul(v) for k, v in obj.items()}
    return obj


def _strip_markdown(obj):
    """Models sometimes emit markdown emphasis (**Python**) despite the
    prompts; our renderers bold technologies themselves, so literal asterisks
    and backticks must never reach the CV or the feedback."""
    if isinstance(obj, str):
        return obj.replace('**', '').replace('`', '')
    if isinstance(obj, list):
        return [_strip_markdown(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _strip_markdown(v) for k, v in obj.items()}
    return obj


def _need(d, key, types, where):
    if not isinstance(d, dict) or key not in d or not isinstance(d[key], types):
        raise SchemaError(f'missing/invalid "{key}" in {where}')
    return d[key]


def _str_list(v):
    return [str(x) for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []


def _clamp_int(v, lo, hi, default=0):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def ensure_extraction(data):
    data = _strip_nul(data)
    _need(data, 'candidate_name', dict, 'extraction')
    _need(data, 'contact', dict, 'extraction')
    data.setdefault('is_cv', True)
    name = data['candidate_name']
    fn = name.get('full_name')
    name['full_name'] = fn.strip() if isinstance(fn, str) and fn.strip() else None
    try:
        name['confidence'] = max(0.0, min(1.0, float(name.get('confidence', 0))))
    except (TypeError, ValueError):
        name['confidence'] = 0.0
    for key in ('skills', 'experience', 'projects', 'education', 'extras'):
        if not isinstance(data.get(key), list):
            data[key] = []
    for exp in data['experience']:
        exp['bullets'] = _str_list(exp.get('bullets'))
    for ex in data['extras']:
        ex['lines'] = _str_list(ex.get('lines'))
    if not isinstance(data.get('flags'), dict):
        data['flags'] = {}
    if not isinstance(data['contact'].get('links'), list):
        data['contact']['links'] = []
    return data


def ensure_critic(data):
    data = _strip_markdown(_strip_nul(data))
    checklist = _need(data, 'rules_checklist', list, 'critic')
    # Exactly one entry per rule, in canonical order; missing rules fail closed.
    by_rule = {}
    for item in checklist:
        if isinstance(item, dict) and item.get('rule') in RULES:
            by_rule.setdefault(item['rule'], {
                'rule': item['rule'],
                'status': item.get('status') if item.get('status') in ('pass', 'partial', 'fail') else 'fail',
                'note': str(item.get('note') or ''),
            })
    data['rules_checklist'] = [
        by_rule.get(r, {'rule': r, 'status': 'fail', 'note': ''}) for r in RULES]
    data['quality_score'] = _clamp_int(data.get('quality_score'), 0, 100)
    data['jd_match'] = (_clamp_int(data['jd_match'], 0, 100)
                        if data.get('jd_match') is not None else None)
    data['verdict'] = str(data.get('verdict') or '')
    data['strengths'] = _str_list(data.get('strengths'))
    data['action_items'] = _str_list(data.get('action_items'))
    if not isinstance(data.get('improvements'), list):
        data['improvements'] = []
    data['improvements'] = [i for i in data['improvements'] if isinstance(i, dict)]
    return data


def rules_score(checklist):
    """pass = 1, partial = ½, rounded — the 'CV Rules X/10' number."""
    raw = sum(1.0 if c['status'] == 'pass' else 0.5 if c['status'] == 'partial' else 0.0
              for c in checklist)
    return min(len(RULES), int(raw + 0.5))


def ensure_optimizer(data):
    data = _strip_markdown(_strip_nul(data))
    cv = _need(data, 'optimized_cv', dict, 'optimizer')
    _need(cv, 'name', str, 'optimized_cv')
    cv.setdefault('title', '')
    cv.setdefault('summary', '')
    for key in ('links', 'skills_groups', 'experience', 'projects', 'education', 'extras'):
        if not isinstance(cv.get(key), list):
            cv[key] = []
    for g in cv['skills_groups']:
        g['skills'] = _str_list(g.get('skills'))
    for exp in cv['experience']:
        exp['bullets'] = _str_list(exp.get('bullets'))
    for ex in cv['extras']:
        ex['lines'] = _str_list(ex.get('lines'))
    if not isinstance(data.get('changes'), list):
        data['changes'] = []
    data['changes'] = [
        {'change_type': c.get('change_type') if c.get('change_type') in CHANGE_TYPES else 'rewrite',
         'section': str(c.get('section') or ''),
         'before': str(c.get('before') or ''),
         'after': str(c.get('after') or ''),
         'reason': str(c.get('reason') or ''),
         'evidence_refs': _str_list(c.get('evidence_refs'))}
        for c in data['changes'] if isinstance(c, dict)]
    if not isinstance(data.get('jd_analysis'), dict):
        data['jd_analysis'] = None
    if data['jd_analysis'] is not None:
        for key in ('strong_matches', 'surfaced', 'not_evidenced'):
            data['jd_analysis'][key] = _str_list(data['jd_analysis'].get(key))
    recs = data.get('career_recommendations')
    data['career_recommendations'] = [
        {'skill': str(r.get('skill') or ''),
         'priority': r.get('priority') if r.get('priority') in ('high', 'medium', 'low') else 'medium',
         'reason_type': r.get('reason_type') if r.get('reason_type') in
             ('target_job_gap', 'role_framework_gap', 'cv_information_gap') else 'role_framework_gap',
         'reason': str(r.get('reason') or ''),
         'cv_evidence': r.get('cv_evidence') if r.get('cv_evidence') in
             ('found', 'partial', 'not_found') else 'not_found',
         'recommendation': str(r.get('recommendation') or ''),
         'cv_instruction': str(r.get('cv_instruction') or '')}
        for r in (recs if isinstance(recs, list) else []) if isinstance(r, dict) and r.get('skill')]
    return data
