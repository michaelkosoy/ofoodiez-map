"""Deterministic validators for the optimized CV — the hard gates the model
output must pass before anything is rendered, stored or shown:

  * residential-address leakage (city-level is the maximum allowed precision)
  * candidate-name preservation (exactly as extracted/confirmed)
  * evidence discipline (no skills/numbers/JD terms that the CV doesn't back)
  * career-recommendation hygiene (never recommend what's already evidenced,
    never phrase "not evidenced" as "you don't know")

Each check returns violation dicts; the pipeline first asks the model to
repair, then applies the deterministic fixes here so nothing dirty can ship.
"""
import re

# ── Address profile & leakage ────────────────────────────────────────────────
_STREET_SUFFIXES = {'street', 'st', 'blvd', 'boulevard', 'ave', 'avenue',
                    'road', 'rd', 'lane', 'ln', 'drive', 'dr', 'way', 'court',
                    'ct', 'place', 'pl', 'רחוב', 'רח', 'שדרות', 'שד', 'דרך'}
_UNIT_WORDS = {'apt', 'apartment', 'suite', 'unit', 'flat', 'floor',
               'דירה', 'קומה', 'כניסה'}

# Patterns that indicate sub-city precision regardless of the original text.
_GENERIC_ADDRESS_PATTERNS = [
    re.compile(r"(?i)\b\d{1,4}[a-z]?\s+(?:[\w'’-]+\s+){0,3}(?:street|st|boulevard|blvd|avenue|ave|road|rd|lane|ln|drive|dr|court|ct|place|pl)\b\.?"),
    re.compile(r"(?i)\b(?:street|boulevard|blvd|avenue|ave|road|rd|lane|ln)\s*,?\s*\d{1,4}\b"),
    re.compile(r"(?i)\b(?:apt|apartment|suite|unit|flat)\.?\s*#?\s*\d+\b"),
    re.compile(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}\b"),        # full UK postcode
    re.compile(r"\b\d{5}-\d{4}\b"),                                   # US ZIP+4
    re.compile(r"(?:רחוב|רח'|שדרות|שד'|דרך)\s+[\w\"'׳״-]+\s*,?\s*\d{1,4}"),
    re.compile(r"(?:דירה|קומה|כניסה)\s*\d+"),
]


def _tokens(text):
    return re.findall(r"[\w'׳״-]+", text or '', re.UNICODE)


def address_profile(canonical):
    """Distill the ORIGINAL evidence's address into (a) the allowed city-level
    location and (b) the forbidden tokens/phrases the final CV must not carry.

    No external geolocation services are ever used — everything derives from
    what the candidate themselves wrote."""
    contact = canonical.get('contact') or {}
    raw = contact.get('location_raw') or ''
    city = (contact.get('city') or '').strip()
    country = (contact.get('country') or '').strip()
    allowed = {t.lower() for t in _tokens(city) + _tokens(country)}

    forbidden_tokens = set()   # matched with word boundaries, case-insensitive
    phrases = set()            # multiword street phrases ("baker street")
    words = _tokens(raw)
    for i, tok in enumerate(words):
        low = tok.lower()
        if low in allowed:
            continue
        if tok.isdigit():
            if len(tok) >= 5:                      # postal code
                forbidden_tokens.add(tok)
        elif re.fullmatch(r'\d+[A-Za-z]', tok):    # house number like 221B
            forbidden_tokens.add(tok)
        elif re.fullmatch(r'[A-Za-z]{1,2}\d{1,2}[A-Za-z]?', tok):  # NW1
            forbidden_tokens.add(tok)
        elif low not in _STREET_SUFFIXES and low not in _UNIT_WORDS and len(low) >= 3:
            # A street-name word: forbid it together with its suffix and with
            # any adjacent house number — but never the bare word alone (a CV
            # may legitimately mention "Dizengoff Center" as a workplace).
            nxt = words[i + 1].lower() if i + 1 < len(words) else ''
            prv = words[i - 1].lower() if i > 0 else ''
            if nxt in _STREET_SUFFIXES:
                phrases.add(f'{low} {nxt}')
            if prv in _STREET_SUFFIXES:
                phrases.add(f'{prv} {low}')
            if (nxt.isdigit() and len(nxt) <= 4) or (prv.isdigit() and len(prv) <= 4):
                phrases.add(f'{low} {nxt}' if nxt.isdigit() else f'{prv} {low}')
    return {'city': city, 'country': country,
            'forbidden_tokens': forbidden_tokens, 'phrases': phrases}


def _phrase_re(phrase):
    parts = [re.escape(p) for p in phrase.split()]
    return re.compile(r'(?i)(?<!\w)' + r'[\s,.-]+'.join(parts) + r'(?!\w)')


def _token_re(tok):
    return re.compile(r'(?i)(?<!\w)' + re.escape(tok) + r'(?!\w)')


def find_address_leaks(text, profile):
    hits = []
    for pat in _GENERIC_ADDRESS_PATTERNS:
        hits += [m.group(0) for m in pat.finditer(text)]
    for tok in profile['forbidden_tokens']:
        if _token_re(tok).search(text):
            hits.append(tok)
    for phrase in profile['phrases']:
        if _phrase_re(phrase).search(text):
            hits.append(phrase)
    return hits


def scrub_address(text, profile):
    """Deterministic removal of address fragments (last-resort hard fix)."""
    for pat in _GENERIC_ADDRESS_PATTERNS:
        text = pat.sub(' ', text)
    for phrase in profile['phrases']:
        text = _phrase_re(phrase).sub(' ', text)
    for tok in profile['forbidden_tokens']:
        text = _token_re(tok).sub(' ', text)
    text = re.sub(r'\s*,\s*(?=,|$)', '', re.sub(r'[ \t]{2,}', ' ', text)).strip(' ,;-\t')
    return text


def iter_cv_strings(cv):
    """Yield (path, value, setter) for every string in the optimized CV."""
    def walk(obj, path):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield from walk(v, path + [k])
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                yield from walk(v, path + [i])
        elif isinstance(obj, str):
            def setter(new, o=obj, p=tuple(path)):
                node = cv
                for key in p[:-1]:
                    node = node[key]
                node[p[-1]] = new
            yield '.'.join(map(str, path)), obj, setter
    yield from walk(cv, [])


def validate_no_address(cv, profile):
    violations = []
    for path, value, _set in iter_cv_strings(cv):
        # URLs may contain street-like tokens coincidentally; still forbidden —
        # simpler and safer to hold links to the same rule.
        for hit in find_address_leaks(value, profile):
            violations.append({'type': 'address', 'path': path,
                               'detail': f'residential-address fragment "{hit}" must not appear (max precision: city)'})
    return violations


def fix_address(cv, profile):
    for _path, value, setter in iter_cv_strings(cv):
        if find_address_leaks(value, profile):
            setter(scrub_address(value, profile))


# ── Candidate name ───────────────────────────────────────────────────────────
def _norm_ws(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()


def validate_name(cv, expected_name):
    if _norm_ws(cv.get('name')) != _norm_ws(expected_name):
        return [{'type': 'name', 'path': 'name',
                 'detail': f'candidate name must be exactly "{expected_name}" '
                           f'(got "{cv.get("name")}") — never shortened, corrected or invented'}]
    return []


# ── Evidence discipline ──────────────────────────────────────────────────────
def derive_claims(canonical):
    """Flatten the canonical extraction into an evidence ledger:
    [{'id', 'section', 'text'}]. Everything the optimizer may build from."""
    claims = []

    def add(section, text):
        if isinstance(text, str) and text.strip():
            claims.append({'id': f'claim_{len(claims):03d}',
                           'section': section, 'text': text.strip()})

    name = (canonical.get('candidate_name') or {})
    add('name', name.get('full_name'))
    contact = canonical.get('contact') or {}
    for key in ('email', 'phone', 'city', 'country'):
        add('contact', contact.get(key))
    for link in contact.get('links') or []:
        add('links', f"{link.get('label', '')} {link.get('url', '')}")
    add('title', canonical.get('title'))
    add('summary', canonical.get('summary'))
    for s in canonical.get('skills') or []:
        add('skills', s.get('name'))
        add('skills', s.get('source_text'))
    for exp in canonical.get('experience') or []:
        add('experience', f"{exp.get('title', '')} — {exp.get('company', '')} {exp.get('dates', '')}")
        for b in exp.get('bullets') or []:
            add('experience', b)
    for p in canonical.get('projects') or []:
        add('projects', f"{p.get('name', '')}: {p.get('description', '')} {p.get('link') or ''}")
    for e in canonical.get('education') or []:
        add('education', f"{e.get('degree', '')} — {e.get('institution', '')} {e.get('dates', '')}")
    for ex in canonical.get('extras') or []:
        add('extras', ex.get('heading'))
        for line in ex.get('lines') or []:
            add('extras', line)
    return claims


def evidence_corpus(claims):
    return '\n'.join(c['text'] for c in claims)


def _word_in(term, text):
    if not term:
        return True
    return bool(re.search(r'(?i)(?<!\w)' + re.escape(term.strip()) + r'(?!\w)', text))


def cv_full_text(cv):
    return '\n'.join(v for _p, v, _s in iter_cv_strings(cv))


_PLACEHOLDER_SPAN = re.compile(r'\[[^\]\n]{0,60}\]')
_NUMBER = re.compile(r'\d[\d,.]*%?')


def validate_evidence(optimizer_out, corpus):
    """Unsupported skills / numbers / JD-term leakage into the optimized CV."""
    cv = optimizer_out['optimized_cv']
    violations = []
    for group in cv.get('skills_groups') or []:
        for skill in group.get('skills') or []:
            if not _word_in(skill, corpus):
                violations.append({'type': 'unsupported_skill', 'path': 'skills_groups',
                                   'detail': f'skill "{skill}" is not evidenced in the CV — remove it'})
    full = cv_full_text(cv)
    jd = optimizer_out.get('jd_analysis') or {}
    for term in jd.get('not_evidenced') or []:
        if _word_in(term, full) and not _word_in(term, corpus):
            violations.append({'type': 'jd_term_added', 'path': 'optimized_cv',
                               'detail': f'JD requirement "{term}" is not evidenced in the CV but appears in the optimized CV — remove it'})
    for term in jd.get('surfaced') or []:
        if not _word_in(term, corpus):
            violations.append({'type': 'surfaced_unevidenced', 'path': 'jd_analysis.surfaced',
                               'detail': f'"{term}" is listed as surfaced but has no evidence in the CV'})
    number_sources = [('summary', cv['summary'])] if cv.get('summary') else []
    for section in ('experience', 'projects'):
        for item in cv.get(section) or []:
            texts = item.get('bullets') or ([item.get('description')] if item.get('description') else [])
            number_sources += [(section, b) for b in texts]
    for section, bullet in number_sources:
        stripped = _PLACEHOLDER_SPAN.sub(' ', bullet)
        for num in _NUMBER.findall(stripped):
            plain = num.replace(',', '').rstrip('%.')
            if plain and plain not in corpus.replace(',', ''):
                violations.append({'type': 'unsupported_number', 'path': section,
                                   'detail': f'number "{num}" in "{bullet[:80]}" does not appear in the CV — '
                                             f'use a [placeholder] or drop it'})
    return violations


def _fix_numbers(text, corpus):
    """Replace unevidenced numbers with an [X] placeholder — degrade the claim,
    never delete the whole bullet (content must survive hard fixes)."""
    plain_corpus = corpus.replace(',', '')

    def repl(m):
        plain = m.group(0).replace(',', '').rstrip('%.')
        return m.group(0) if (not plain or plain in plain_corpus) else '[X]'

    parts = re.split(r'(\[[^\]\n]{0,60}\])', text)   # leave existing [placeholders] alone
    return ''.join(p if p.startswith('[') else _NUMBER.sub(repl, p) for p in parts)


def drop_unevidenced(optimizer_out, corpus):
    """Deterministic hard fix: strip skills that lack evidence; downgrade
    unevidenced numbers to [X]; drop a bullet only when it carries a JD term
    the CV doesn't back (the term IS the claim there)."""
    cv = optimizer_out['optimized_cv']
    for group in cv.get('skills_groups') or []:
        group['skills'] = [s for s in group['skills'] if _word_in(s, corpus)]
    cv['skills_groups'] = [g for g in cv.get('skills_groups') or [] if g['skills']]
    jd = optimizer_out.get('jd_analysis') or {}
    bad_terms = [t for t in (jd.get('not_evidenced') or []) if not _word_in(t, corpus)]

    def clean(text):
        if any(_word_in(t, text) for t in bad_terms):
            return None
        return _fix_numbers(text, corpus)

    for exp in cv.get('experience') or []:
        exp['bullets'] = [c for c in (clean(b) for b in exp['bullets']) if c]
    for proj in list(cv.get('projects') or []):
        if proj.get('description'):
            cleaned = clean(proj['description'])
            if cleaned is None:
                cv['projects'].remove(proj)
            else:
                proj['description'] = cleaned
    if cv.get('summary'):
        cv['summary'] = _fix_numbers(cv['summary'], corpus)
    if jd:
        jd['surfaced'] = [t for t in (jd.get('surfaced') or []) if _word_in(t, corpus)]


# ── Content floor ────────────────────────────────────────────────────────────
# A repair round must never be allowed to "fix" violations by deleting the CV.
def total_bullets(cv_or_canonical):
    return sum(len(e.get('bullets') or []) for e in cv_or_canonical.get('experience') or [])


def validate_content_floor(optimizer_out, canonical):
    cv = optimizer_out['optimized_cv']
    violations = []
    for section in ('experience', 'education'):
        if (canonical.get(section) or []) and not (cv.get(section) or []):
            violations.append({'type': 'content_loss', 'path': section,
                               'detail': f'the original CV has {section} but the optimized CV '
                                         f'lost it entirely — it must be rewritten, not removed'})
    if total_bullets(canonical) >= 2 and total_bullets(cv) == 0 and (cv.get('experience') or []):
        violations.append({'type': 'content_loss', 'path': 'experience',
                           'detail': 'every experience bullet was lost — rewrite them from '
                                     'the evidence, do not delete them'})
    if (canonical.get('summary') or '').strip() and not (cv.get('summary') or '').strip():
        violations.append({'type': 'content_loss', 'path': 'summary',
                           'detail': 'the summary was lost — rewrite it from the evidence'})
    return violations


def restore_from_canonical(optimizer_out, canonical, profile):
    """Last-resort content floor: lost sections come back VERBATIM from the
    canonical extraction (address-scrubbed) — verbatim original text is
    evidence-safe by construction, just not optimized."""
    cv = optimizer_out['optimized_cv']

    def scrub(text):
        return scrub_address(text or '', profile)

    restored = []
    if ((canonical.get('experience') or []) and
            (not cv.get('experience') or total_bullets(cv) == 0 < total_bullets(canonical))):
        cv['experience'] = [{'company': scrub(e.get('company')), 'title': scrub(e.get('title')),
                             'dates': e.get('dates') or '',
                             'bullets': [scrub(b) for b in e.get('bullets') or []]}
                            for e in canonical['experience']]
        restored.append('experience')
    if (canonical.get('education') or []) and not (cv.get('education') or []):
        cv['education'] = [{'institution': scrub(e.get('institution')),
                            'degree': scrub(e.get('degree')), 'dates': e.get('dates') or ''}
                           for e in canonical['education']]
        restored.append('education')
    if (canonical.get('projects') or []) and not (cv.get('projects') or []):
        cv['projects'] = [{'name': scrub(p.get('name')), 'tech': None,
                           'description': scrub(p.get('description')), 'link': p.get('link')}
                          for p in canonical['projects']]
        restored.append('projects')
    if (canonical.get('extras') or []) and not (cv.get('extras') or []):
        cv['extras'] = [{'heading': scrub(x.get('heading')),
                         'lines': [scrub(l) for l in x.get('lines') or []]}
                        for x in canonical['extras']]
        restored.append('extras')
    if (canonical.get('summary') or '').strip() and not (cv.get('summary') or '').strip():
        cv['summary'] = scrub(canonical['summary'])
        restored.append('summary')
    contact_links = (canonical.get('contact') or {}).get('links') or []
    if contact_links and not (cv.get('links') or []):
        cv['links'] = [{'label': l.get('label') or '', 'url': l.get('url') or ''}
                       for l in contact_links if l.get('url')]
    for section in restored:
        optimizer_out['changes'].append({
            'change_type': 'keep', 'section': section, 'before': '', 'after': '',
            'reason': f'התוכן המקורי של {section} נשמר כפי שהוא (שחזור אוטומטי לאחר שהמודל השמיט אותו).',
            'evidence_refs': []})
    return restored


# ── Career recommendations ───────────────────────────────────────────────────
# "Not evidenced in the CV" must never be phrased as "you don't know X".
WORDING_FORBIDDEN = [
    re.compile(r"(?i)\byou (?:don'?t|do not) know\b"),
    re.compile(r"(?i)\byou (?:don'?t|do not) have (?:any\s+)?[\w /-]{0,30}(?:experience|knowledge)"),
    re.compile(r"(?i)\byou have no [\w /-]{0,30}(?:experience|knowledge)"),
    re.compile(r"(?i)\b(?:candidate|he|she|they) (?:doesn'?t|does not|don'?t|do not) know\b"),
    re.compile(r"אין ל(?:ך|כם|כן) (?:ניסיון|ידע)"),
    re.compile(r"את[הם]? לא (?:יודעת?|יודעים|מכירה?|מכירים)"),
    re.compile(r"אינ(?:ך|כם) (?:יודעת?|מכירה?)"),
    re.compile(r"חסר ל(?:ך|כם) (?:ניסיון|ידע)"),
]

MAX_RECOMMENDATIONS = 5


def validate_recommendations(optimizer_out, corpus):
    violations = []
    cv_text = cv_full_text(optimizer_out['optimized_cv'])
    for i, rec in enumerate(optimizer_out.get('career_recommendations') or []):
        skill = rec.get('skill', '')
        where = f'career_recommendations[{i}]'
        if rec.get('cv_evidence') == 'not_found' and _word_in(skill, corpus):
            violations.append({'type': 'rec_already_evidenced', 'path': where,
                               'detail': f'"{skill}" IS evidenced in the CV — do not recommend learning it; '
                                         f'surface the existing evidence instead'})
        if rec.get('cv_evidence') == 'not_found' and _word_in(skill, cv_text):
            violations.append({'type': 'rec_leaked_into_cv', 'path': where,
                               'detail': f'"{skill}" is a learning suggestion, not CV content — it must not '
                                         f'appear in the optimized CV'})
    return violations


def validate_wording(feedback_texts):
    """feedback_texts: iterable of (path, text) covering recs/verdict/improvements."""
    violations = []
    for path, text in feedback_texts:
        for pat in WORDING_FORBIDDEN:
            m = pat.search(text or '')
            if m:
                violations.append({'type': 'wording', 'path': path,
                                   'detail': f'"{m.group(0)}" — absence of evidence is not absence of knowledge; '
                                             f'phrase it as "isn\'t evidenced in the CV" / "לא נראה בקורות החיים"'})
    return violations


def fix_recommendations(optimizer_out, corpus):
    """Deterministic hard fix: drop recs that are already evidenced or still
    use forbidden wording; cap at MAX_RECOMMENDATIONS ordered by priority."""
    order = {'high': 0, 'medium': 1, 'low': 2}
    kept = []
    for rec in optimizer_out.get('career_recommendations') or []:
        if rec.get('cv_evidence') == 'not_found' and _word_in(rec.get('skill', ''), corpus):
            continue
        text = f"{rec.get('reason', '')} {rec.get('recommendation', '')}"
        if any(p.search(text) for p in WORDING_FORBIDDEN):
            continue
        kept.append(rec)
    kept.sort(key=lambda r: order.get(r.get('priority'), 1))
    optimizer_out['career_recommendations'] = kept[:MAX_RECOMMENDATIONS]


def rec_feedback_texts(optimizer_out):
    for i, rec in enumerate(optimizer_out.get('career_recommendations') or []):
        yield f'career_recommendations[{i}].reason', rec.get('reason', '')
        yield f'career_recommendations[{i}].recommendation', rec.get('recommendation', '')


def critic_feedback_texts(critic_out):
    yield 'verdict', critic_out.get('verdict', '')
    for i, s in enumerate(critic_out.get('strengths') or []):
        yield f'strengths[{i}]', s
    for i, imp in enumerate(critic_out.get('improvements') or []):
        yield f'improvements[{i}].issue', imp.get('issue', '')
        yield f'improvements[{i}].fix', imp.get('fix', '')
    for i, a in enumerate(critic_out.get('action_items') or []):
        yield f'action_items[{i}]', a


def drop_forbidden_feedback(critic_out):
    """Hard fix for critic text that still misphrases absence-of-evidence."""
    def clean_list(items, texts_of):
        return [it for it in items
                if not any(p.search(texts_of(it)) for p in WORDING_FORBIDDEN)]
    critic_out['strengths'] = clean_list(critic_out.get('strengths') or [], lambda s: s)
    critic_out['action_items'] = clean_list(critic_out.get('action_items') or [], lambda s: s)
    critic_out['improvements'] = clean_list(
        critic_out.get('improvements') or [],
        lambda i: f"{i.get('issue', '')} {i.get('fix', '')}")
    for pat in WORDING_FORBIDDEN:
        critic_out['verdict'] = pat.sub('לא נראה בקורות החיים', critic_out.get('verdict', ''))
