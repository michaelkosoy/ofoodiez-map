"""Address privacy, name preservation, evidence and wording validators."""
from cv_review import validators
from cv_review.storage import sanitize_name


def _canonical(location_raw, city, country='Israel', skills=(), bullets=()):
    return {
        'candidate_name': {'full_name': 'Jane Smith', 'confidence': 0.99,
                           'source_text': 'Jane Smith'},
        'contact': {'email': 'jane@example.com', 'phone': '+972500000000',
                    'location_raw': location_raw, 'city': city, 'country': country,
                    'links': []},
        'title': 'Backend Engineer', 'summary': 'Backend developer.',
        'skills': [{'name': s, 'source_text': s} for s in skills],
        'experience': [{'company': 'Acme', 'title': 'Engineer', 'dates': '2023-2025',
                        'bullets': list(bullets)}],
        'projects': [], 'education': [], 'extras': [],
        'flags': {'language': 'en'},
    }


# ── Address (§ residential-address regression tests) ─────────────────────────
def test_baker_street_regression():
    profile = validators.address_profile(
        _canonical('221B Baker Street, London NW1', 'London', 'UK'))
    assert validators.find_address_leaks('221B Baker Street', profile)
    assert validators.find_address_leaks('Based near NW1', profile)
    assert validators.find_address_leaks('Baker Street area', profile)
    assert not validators.find_address_leaks('London', profile)
    assert not validators.find_address_leaks('London, UK', profile)
    cleaned = validators.scrub_address('Jane — 221B Baker Street, London NW1', profile)
    assert '221B' not in cleaned and 'NW1' not in cleaned and 'Baker' not in cleaned
    assert 'London' in cleaned


def test_dizengoff_address_regression():
    profile = validators.address_profile(
        _canonical('12 Dizengoff Street, Apt 3, Tel Aviv 6433212', 'Tel Aviv'))
    for leak in ('12 Dizengoff Street', 'Apt 3', '6433212', 'Dizengoff Street'):
        assert validators.find_address_leaks(leak, profile), leak
    assert not validators.find_address_leaks('Tel Aviv', profile)
    assert not validators.find_address_leaks('Tel Aviv, Israel', profile)


def test_rothschild_hebrew_and_generic_patterns():
    profile = validators.address_profile(
        _canonical('14 Rothschild Blvd, Apt 5, Tel Aviv 6688101', 'Tel Aviv'))
    assert validators.find_address_leaks('14 Rothschild Blvd', profile)
    assert validators.find_address_leaks('Apartment: Apt 5', profile)
    assert validators.find_address_leaks('6688101', profile)
    # Generic sub-city patterns are caught even without profile tokens
    assert validators.find_address_leaks('רחוב הרצל 10', profile)
    assert validators.find_address_leaks('קומה 3', profile)


def test_numbers_in_bullets_not_false_flagged_as_address():
    profile = validators.address_profile(_canonical('Tel Aviv', 'Tel Aviv'))
    assert not validators.find_address_leaks('Improved latency by 14% for 6,000 users', profile)


def test_validate_no_address_walks_all_fields():
    profile = validators.address_profile(
        _canonical('12 Dizengoff Street, Tel Aviv 6433212', 'Tel Aviv'))
    cv = {'name': 'Jane Smith', 'title': 'Engineer',
          'summary': 'Lives at 12 Dizengoff Street.',
          'location': 'Tel Aviv 6433212',
          'skills_groups': [], 'experience': [], 'projects': [],
          'education': [], 'extras': [], 'links': []}
    violations = validators.validate_no_address(cv, profile)
    paths = {v['path'] for v in violations}
    assert 'summary' in paths and 'location' in paths
    validators.fix_address(cv, profile)
    assert not validators.validate_no_address(cv, profile)
    assert 'Tel Aviv' in cv['location']


# ── Name (§ candidate identity) ──────────────────────────────────────────────
def test_name_must_match_exactly():
    assert validators.validate_name({'name': 'Michael K.'}, 'Michael Kosoy')
    assert validators.validate_name({'name': 'John Doe'}, 'Jane Smith')
    assert not validators.validate_name({'name': 'Jane  Smith'}, 'Jane Smith')  # ws-normalized


# ── Evidence ─────────────────────────────────────────────────────────────────
def _opt(skills, bullets=(), not_evidenced=(), recs=()):
    return {
        'optimized_cv': {'name': 'Jane Smith', 'title': 'Backend Engineer',
                         'summary': 'Backend developer.', 'location': 'Tel Aviv',
                         'email': None, 'phone': None, 'links': [],
                         'skills_groups': [{'group': 'Skills', 'skills': list(skills)}],
                         'experience': [{'company': 'Acme', 'title': 'Engineer',
                                         'dates': '2023', 'bullets': list(bullets)}],
                         'projects': [], 'education': [], 'extras': []},
        'changes': [], 'jd_analysis': {'strong_matches': [], 'surfaced': [],
                                       'not_evidenced': list(not_evidenced)},
        'career_recommendations': list(recs),
    }


def test_unsupported_skill_flagged_and_dropped():
    canonical = _canonical('Tel Aviv', 'Tel Aviv', skills=['Python', 'Kafka'],
                           bullets=['Built pipelines with Kafka'])
    corpus = validators.evidence_corpus(validators.derive_claims(canonical))
    opt = _opt(['Python', 'Kafka', 'Kubernetes'], not_evidenced=['Kubernetes'])
    violations = validators.validate_evidence(opt, corpus)
    assert any(v['type'] == 'unsupported_skill' and 'Kubernetes' in v['detail']
               for v in violations)
    validators.drop_unevidenced(opt, corpus)
    assert 'Kubernetes' not in validators.cv_full_text(opt['optimized_cv'])
    assert 'Kafka' in validators.cv_full_text(opt['optimized_cv'])


def test_unsupported_number_flagged_placeholder_ok():
    canonical = _canonical('Tel Aviv', 'Tel Aviv', skills=['Python'],
                           bullets=['Served 6,000 users with Python'])
    corpus = validators.evidence_corpus(validators.derive_claims(canonical))
    ok = _opt(['Python'], bullets=['Scaled service to 6,000 users using Python',
                                   'Cut costs by [X%] via caching'])
    assert not validators.validate_evidence(ok, corpus)
    bad = _opt(['Python'], bullets=['Improved throughput by 73%'])
    assert any(v['type'] == 'unsupported_number' for v in validators.validate_evidence(bad, corpus))


def test_rec_for_evidenced_skill_flagged():
    """CV says 'Managed Kubernetes deployments on EKS' → never recommend
    'learn Kubernetes'; surface the evidence instead."""
    canonical = _canonical('Tel Aviv', 'Tel Aviv', skills=['Python'],
                           bullets=['Managed Kubernetes deployments on EKS'])
    corpus = validators.evidence_corpus(validators.derive_claims(canonical))
    opt = _opt(['Python'], recs=[{'skill': 'Kubernetes', 'priority': 'high',
                                  'reason_type': 'target_job_gap', 'reason': 'נדרש במשרה',
                                  'cv_evidence': 'not_found',
                                  'recommendation': 'למדו קוברנטיס', 'cv_instruction': ''}])
    violations = validators.validate_recommendations(opt, corpus)
    assert any(v['type'] == 'rec_already_evidenced' for v in violations)
    validators.fix_recommendations(opt, corpus)
    assert opt['career_recommendations'] == []


# ── Wording (§ absent vs unknown) ────────────────────────────────────────────
def test_forbidden_wording_detected():
    for text in ("You don't know Kubernetes.",
                 'You have no AWS experience',
                 "you do not have any cloud experience",
                 'אין לך ניסיון ב-AWS',
                 'אתה לא מכיר Kubernetes'):
        assert validators.validate_wording([('x', text)]), text


def test_allowed_wording_passes():
    for text in ("Kubernetes isn't evidenced in your CV.",
                 'AWS experience isn\'t evidenced in the CV you uploaded.',
                 'Kubernetes לא נראה בקורות החיים שהעלית'):
        assert not validators.validate_wording([('x', text)]), text


# ── Filenames (names are labels, UUIDs are security identifiers) ────────────
def test_sanitize_name():
    assert sanitize_name('Michael Kosoy') == 'Michael_Kosoy'
    traversal = sanitize_name('../../etc/passwd')
    assert '/' not in traversal and '..' not in traversal and traversal
    assert '/' not in sanitize_name('a/b\\c:d*e?f"g<h>i|j')
    assert sanitize_name('a\x00b\nc') == 'a_b_c' or '\x00' not in sanitize_name('a\x00b\nc')
    assert sanitize_name('') == 'Candidate'
    assert sanitize_name('..') == 'Candidate'
    assert len(sanitize_name('x' * 500)) <= 64
    assert sanitize_name('משה כהן')  # Hebrew names survive as labels
