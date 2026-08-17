"""End-to-end pipeline enforcement with a scripted fake model — candidate
identity, address privacy, evidence discipline, recommendations, summaries,
and the zero-HTTP guarantee (conftest blocks all real HTTP)."""
import json

import pytest

import cv_fake_data as fake
from cv_review import pipeline
from cv_review.docx_inspect import inspect_docx
from cv_review.jobspec import normalize_job_input


def run(responses, *, job=None, owner=None, cv_text=b'Jane Smith\nBackend CV text',
        ext='.txt', consent=False):
    model = fake.FakeModel(responses)
    payload, review = pipeline.start_review(
        file_bytes=cv_text, filename=f'cv{ext}', ext=ext,
        job=job or fake.NO_JOB, consent=consent, owner_user_id=owner,
        key='fake-key', generate=model)
    return payload, review, model


def good_responses(**opt_kw):
    return {'extract': fake.make_extraction(),
            'critic': fake.make_critic(),
            'critic_optimized': fake.make_critic(quality=93, jd_match=85),
            'optimize': fake.make_optimizer(**opt_kw),
            'repair': lambda parts: fake.make_optimizer(**opt_kw)}


# ── Candidate identity (§ name tests) ────────────────────────────────────────
def test_name_preserved_end_to_end(app_ctx):
    payload, review, _ = run(good_responses())
    assert payload['candidate']['name'] == 'Jane Smith'
    assert payload['optimized_cv']['name'] == 'Jane Smith'
    assert review.candidate_name == 'Jane Smith'
    assert 'Jane Smith' in payload['optimized_text']


def test_account_name_independence(app_ctx):
    """Logged-in user #42 ('Michael') uploads Jane Smith's CV → candidate is
    Jane Smith, never the account owner."""
    payload, review, _ = run(good_responses(), owner=42)
    assert review.owner_user_id == 42
    assert payload['candidate']['name'] == 'Jane Smith'


def test_shortened_name_is_forced_back(app_ctx):
    responses = good_responses()
    responses['optimize'] = fake.make_optimizer(name='Jane S.')
    responses['repair'] = fake.make_optimizer(name='Jane S.')   # repair misbehaves too
    payload, _, _ = run(responses)
    assert payload['optimized_cv']['name'] == 'Jane Smith'


def test_no_name_invention_asks_for_confirmation(app_ctx):
    responses = good_responses()
    responses['extract'] = fake.make_extraction(name=None, confidence=0.0)
    payload, review, model = run(responses)
    assert payload['status'] == 'needs_name_confirmation'
    assert review.status == 'pending_name'
    assert 'John Doe' not in json.dumps(payload)
    # user confirms → pipeline resumes without re-extraction
    result = pipeline.resume_review(review, 'Jane Smith', key='fake-key', generate=model)
    assert result['status'] == 'complete'
    assert result['candidate']['name'] == 'Jane Smith'
    assert model.purposes.count('extract') == 1


def test_low_confidence_name_asks_for_confirmation(app_ctx):
    responses = good_responses()
    responses['extract'] = fake.make_extraction(name='J. Smith?', confidence=0.4)
    payload, _, _ = run(responses)
    assert payload['status'] == 'needs_name_confirmation'
    assert payload['guessed_name'] == 'J. Smith?'


# ── Residential-address privacy (§ address tests) ───────────────────────────
def test_address_never_reaches_output(app_ctx):
    responses = good_responses()
    leaky = fake.make_optimizer(
        summary='Backend engineer at 12 Dizengoff Street, Apt 3 skilled in Python.',
        location='Tel Aviv 6433212')
    responses['optimize'] = leaky
    responses['repair'] = leaky   # model refuses to fix → deterministic scrub
    payload, review, _ = run(responses)
    text = payload['optimized_text']
    for leak in ('12 Dizengoff', 'Apt 3', '6433212', 'Dizengoff Street'):
        assert leak not in text, leak
    assert 'Tel Aviv' in text
    assert any(c['change_type'] == 'location_redaction' for c in payload['changes'])
    assert '12 Dizengoff' not in review.optimized_text


def test_location_redaction_recorded_even_when_model_omits_it(app_ctx):
    payload, _, _ = run(good_responses())
    redactions = [c for c in payload['changes'] if c['change_type'] == 'location_redaction']
    assert len(redactions) == 1
    assert '12 Dizengoff Street' in redactions[0]['before']
    assert redactions[0]['after'] == 'Tel Aviv'


# ── Evidence & career recommendations (§ K8s scenarios) ─────────────────────
def test_jd_gap_recommended_but_never_added_to_cv(app_ctx):
    """JD wants Kubernetes; CV has no Kubernetes evidence. A recommendation is
    allowed — CV content is not, even when the model keeps trying."""
    responses = good_responses()
    cheating = fake.make_optimizer(
        skills=('Python', 'PostgreSQL', 'Kafka', 'Kubernetes'),
        bullets=('Built REST APIs in Python serving 6,000 users',
                 'Deployed services with Kubernetes'),
        not_evidenced=('Kubernetes', 'AWS'), recs=(fake.K8S_REC,))
    responses['optimize'] = cheating
    responses['repair'] = cheating
    payload, _, _ = run(responses, job=fake.JOB)
    assert 'Kubernetes' not in payload['optimized_text']
    recs = payload['career_recommendations']
    assert any(r['skill'] == 'Kubernetes' for r in recs)
    assert 'Kubernetes' in payload['jd_analysis']['not_evidenced']


def test_evidenced_kubernetes_not_recommended(app_ctx):
    """CV explicitly says 'Managed Kubernetes deployments on EKS' → no 'learn
    Kubernetes' recommendation; the skill may stay in the CV."""
    responses = good_responses()
    responses['extract'] = fake.make_extraction(
        skills=('Python', 'Kubernetes'),
        bullets=('Managed Kubernetes deployments on EKS',))
    evidenced = fake.make_optimizer(
        skills=('Python', 'Kubernetes'),
        bullets=('Managed Kubernetes deployments on EKS',),
        summary='Backend engineer with Kubernetes experience on EKS.',
        recs=(fake.K8S_REC,))
    responses['optimize'] = evidenced
    responses['repair'] = evidenced
    payload, _, _ = run(responses, job=fake.JOB)
    assert all(r['skill'] != 'Kubernetes' for r in payload['career_recommendations'])
    assert 'Kubernetes' in payload['optimized_text']


def test_forbidden_wording_in_recs_is_removed(app_ctx):
    bad_rec = dict(fake.K8S_REC, reason="You don't know Kubernetes.")
    responses = good_responses()
    responses['optimize'] = fake.make_optimizer(recs=(bad_rec,))
    responses['repair'] = fake.make_optimizer(recs=(bad_rec,))
    payload, _, _ = run(responses, job=fake.JOB)
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "don't know" not in dumped and "אין לך ניסיון" not in dumped


def test_recommendations_capped_at_five(app_ctx):
    recs = tuple(dict(fake.K8S_REC, skill=f'Skill{i}',
                      reason='לא נראה בקורות החיים.') for i in range(9))
    responses = good_responses()
    responses['optimize'] = fake.make_optimizer(recs=recs)
    payload, _, _ = run(responses, job=fake.JOB)
    assert len(payload['career_recommendations']) <= 5


# ── Job URLs: zero HTTP (§ URL tests; conftest kills any real request) ──────
def test_jd_with_url_normalized_and_never_fetched(app_ctx, no_real_http):
    raw_jd = ('We are hiring a Backend Engineer. ' * 20
              + 'Apply here: https://www.linkedin.com/jobs/view/12345')
    job = normalize_job_input('Backend Engineer', raw_jd, '')
    assert job['removed_urls'] == ['https://www.linkedin.com/jobs/view/12345']
    payload, review, _ = run(good_responses(), job=job)
    assert payload['status'] == 'complete'
    assert 'linkedin.com' not in (review.job_description or '')
    assert no_real_http == []   # ZERO HTTP requests were attempted


# ── Summaries & scores are structural, not narrated (§ change summary) ──────
def test_change_summary_counts_match_ledger(app_ctx):
    payload, _, _ = run(good_responses())
    non_keep = [c for c in payload['changes'] if c['change_type'] != 'keep']
    assert payload['change_summary']['total_changes'] == len(non_keep)
    assert payload['change_summary']['lines']


def test_scores_shape(app_ctx):
    payload, _, _ = run(good_responses(), job=fake.JOB)
    s = payload['scores']
    assert s['rules']['total'] == 10
    assert s['quality'] == {'before': 68, 'after': 93}
    assert s['jd_match'] == {'before': 61, 'after': 85}


def test_no_jd_means_no_jd_match(app_ctx):
    responses = good_responses()
    responses['critic'] = fake.make_critic(jd_match=None)
    responses['critic_optimized'] = fake.make_critic(quality=90, jd_match=None)
    payload, _, _ = run(responses, job=fake.NO_JOB)
    assert payload['scores']['jd_match'] is None


# ── Files, storage, misc ─────────────────────────────────────────────────────
def test_generated_files_valid_and_clean(app_ctx):
    payload, review, _ = run(good_responses(), consent=True)
    assert review.status == 'complete'
    assert review.talent_pool_consent is True
    assert inspect_docx(review.optimized_docx) == []
    assert review.optimized_pdf.startswith(b'%PDF')
    assert 'Jane Smith' in review.optimized_text
    assert review.original_file == b'Jane Smith\nBackend CV text'
    assert set(payload['downloads']) == {'docx', 'pdf', 'txt'}
    usage = review.usage
    assert usage['calls'] >= 4 and usage['input_tokens'] > 0


def test_docx_upload_goes_through_sandbox(app_ctx):
    import cv_evil_docs as evil
    payload, _, _ = run(good_responses(), cv_text=evil.good_docx(), ext='.docx')
    assert payload['status'] == 'complete'
    with pytest.raises(pipeline.PipelineError) as exc:
        run(good_responses(), cv_text=evil.vba_project_docx(), ext='.docx')
    assert exc.value.status == 400
    assert 'Macro' in exc.value.user_message


def test_pdf_magic_checked(app_ctx):
    with pytest.raises(pipeline.PipelineError) as exc:
        run(good_responses(), cv_text=b'not a pdf', ext='.pdf')
    assert exc.value.status == 400


def test_not_a_cv_gets_review_only(app_ctx):
    responses = good_responses()
    responses['extract'] = fake.make_extraction(is_cv=False)
    payload, review, model = run(responses)
    assert payload['status'] == 'not_a_cv'
    assert 'optimize' not in model.purposes
    assert review.status == 'complete' and review.optimized_docx is None
