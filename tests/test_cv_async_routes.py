"""Route-level tests for the async review flow: mandatory consent, background
processing + polling, name-confirmation resume, failure surfacing, terms page."""
import io
import os
import time

import pytest
from flask import Flask

import cv_fake_data as fake
from cv_review import gemini

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from database.models import db
    from cv_review import cv_review_bp
    app = Flask('cvtest',
                template_folder=os.path.join(ROOT, 'app', 'templates'),
                static_folder=os.path.join(ROOT, 'app', 'static'))
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f'sqlite:///{tmp_path}/t.db',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # background worker threads share the sqlite file
        SQLALCHEMY_ENGINE_OPTIONS={'connect_args': {'check_same_thread': False}},
        SECRET_KEY='test',
    )
    db.init_app(app)
    app.register_blueprint(cv_review_bp)
    with app.app_context():
        db.create_all()
    monkeypatch.setenv('GEMINI_API_KEY', 'fake-key')
    c = app.test_client()
    with c.session_transaction() as s:
        s['cv_review_unlocked'] = True
    return c


def _post_cv(client, consent='1', **extra):
    data = {'cv': (io.BytesIO(b'Jane Smith\nBackend CV text'), 'cv.txt'),
            'talent_pool_consent': consent}
    data.update(extra)
    return client.post('/api/hitech/cv-review', data=data)


def _poll_until_done(client, review_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f'/api/hitech/cv-review/{review_id}/status').get_json()
        if data.get('status') != 'processing':
            return data
        time.sleep(0.05)
    raise AssertionError('review never left processing')


def test_consent_is_required(client):
    resp = _post_cv(client, consent='0')
    assert resp.status_code == 400
    assert 'storage terms' in resp.get_json()['error']
    resp = client.post('/api/hitech/cv-review',
                       data={'cv': (io.BytesIO(b'x'), 'cv.txt')})  # no field at all
    assert resp.status_code == 400


def test_async_flow_completes_and_downloads(client, monkeypatch):
    monkeypatch.setattr(gemini, 'generate_json', fake.FakeModel({
        'extract': fake.make_extraction(),
        'critic': fake.make_critic(),
        'critic_optimized': fake.make_critic(quality=93, jd_match=None),
        'optimize': fake.make_optimizer(),
        'repair': fake.make_optimizer()}))
    resp = _post_cv(client)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'processing' and body['review_id']
    data = _poll_until_done(client, body['review_id'])
    assert data['status'] == 'complete'
    assert data['candidate']['name'] == 'Jane Smith'
    assert data['optimized_text'].startswith('Jane Smith')
    dl = client.get(data['downloads']['docx'])
    assert dl.status_code == 200 and dl.data[:2] == b'PK'


def test_async_name_confirmation_resume(client, monkeypatch):
    monkeypatch.setattr(gemini, 'generate_json', fake.FakeModel({
        'extract': fake.make_extraction(name=None, confidence=0.0),
        'critic': fake.make_critic(),
        'critic_optimized': fake.make_critic(quality=90),
        'optimize': fake.make_optimizer(),
        'repair': fake.make_optimizer()}))
    body = _post_cv(client).get_json()
    data = _poll_until_done(client, body['review_id'])
    assert data['status'] == 'needs_name_confirmation'
    resp = client.post('/api/hitech/cv-review/confirm-name',
                       json={'review_id': body['review_id'], 'name': 'Jane Smith'})
    assert resp.get_json()['status'] == 'processing'
    data = _poll_until_done(client, body['review_id'])
    assert data['status'] == 'complete' and data['candidate']['name'] == 'Jane Smith'


def test_failure_is_surfaced_with_real_message(client, monkeypatch):
    def exploding(parts, schema, *, purpose, usage, key, **kw):
        raise gemini.GeminiError('boom', 'The AI reviewer is at capacity right now. '
                                         'Please try again in a few minutes.')
    monkeypatch.setattr(gemini, 'generate_json', exploding)
    body = _post_cv(client).get_json()
    data = _poll_until_done(client, body['review_id'])
    assert data['status'] == 'failed'
    assert 'capacity' in data['error']


def test_status_requires_ownership(client, monkeypatch):
    monkeypatch.setattr(gemini, 'generate_json', fake.FakeModel({
        'extract': fake.make_extraction(), 'critic': fake.make_critic(),
        'critic_optimized': fake.make_critic(), 'optimize': fake.make_optimizer(),
        'repair': fake.make_optimizer()}))
    body = _post_cv(client).get_json()
    with client.session_transaction() as s:
        s['cv_review_ids'] = []          # different visitor
    resp = client.get(f"/api/hitech/cv-review/{body['review_id']}/status")
    assert resp.status_code == 404


def test_terms_page_renders(client):
    resp = client.get('/hitech/cv-review/terms')
    assert resp.status_code == 200
    assert b'What We Store' in resp.data and b'info@ofoodiez.com' in resp.data
