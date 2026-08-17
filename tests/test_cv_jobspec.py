"""Job-input rules: text only, URLs rejected/stripped, never fetched (§ job URLs)."""
import pytest

from cv_review.jobspec import (JobInputError, URL_REJECT_MESSAGE,
                               normalize_job_input)


def test_linkedin_url_only_rejected():
    with pytest.raises(JobInputError) as exc:
        normalize_job_input('', 'https://www.linkedin.com/jobs/view/12345', '')
    assert str(exc.value) == URL_REJECT_MESSAGE


def test_www_url_rejected():
    with pytest.raises(JobInputError):
        normalize_job_input('', 'www.company.com/jobs/123', '')


def test_bare_domain_rejected():
    with pytest.raises(JobInputError):
        normalize_job_input('', 'company.com', '')


def test_greenhouse_lever_workday_rejected():
    for url in ('https://boards.greenhouse.io/acme/jobs/1',
                'https://jobs.lever.co/acme/1',
                'https://acme.wd5.myworkdayjobs.com/en-US/jobs/1'):
        with pytest.raises(JobInputError):
            normalize_job_input('', url, '')


def test_url_in_title_rejected():
    with pytest.raises(JobInputError):
        normalize_job_input('https://linkedin.com/jobs/view/1', '', '')


def test_incidental_url_stripped_not_rejected():
    jd = ('We are hiring a Senior Backend Engineer. ' * 60
          + 'Requirements: Python, PostgreSQL, Kafka, Kubernetes. '
          + 'Learn more at https://company.com/careers')
    out = normalize_job_input('Senior Backend Engineer', jd, '')
    assert out['removed_urls'] == ['https://company.com/careers']
    assert 'https://company.com' not in out['job_description']
    assert 'Kubernetes' in out['job_description']


def test_tech_terms_with_dots_survive():
    jd = ('Backend Engineer role. ' * 10
          + 'Stack: ASP.NET, Node.js, socket.io and Vue.js. Strong SQL required.')
    out = normalize_job_input('', jd, '')
    assert 'ASP.NET' in out['job_description']
    assert 'socket.io' in out['job_description']


def test_size_limits():
    with pytest.raises(JobInputError):
        normalize_job_input('x' * 201, '', '')
    with pytest.raises(JobInputError):
        normalize_job_input('', 'x' * 30_001, '')
    with pytest.raises(JobInputError):
        normalize_job_input('', '', 'x' * 2_001)


def test_control_chars_removed():
    out = normalize_job_input('Back\x00end', 'A real job description with plenty of text about the role.', 'note\x07')
    assert '\x00' not in out['job_title'] and '\x07' not in out['instructions']


def test_empty_inputs_fine():
    out = normalize_job_input(None, None, None)
    assert out == {'job_title': '', 'job_description': '', 'instructions': '',
                   'removed_urls': []}
