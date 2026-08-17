import pytest
from flask import Flask


@pytest.fixture()
def app_ctx():
    """Minimal Flask app + in-memory DB for pipeline tests (the real app.py
    boots background threads we don't want under pytest)."""
    from database.models import db
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    """Every test runs with real HTTP disabled — any attempted network call
    (e.g. fetching a job URL) fails loudly. Proves the backend performs ZERO
    HTTP requests during reviews driven by the fake model."""
    import requests.adapters

    attempted = []

    def _blocked(self, request, *a, **kw):
        attempted.append(request.url)
        raise AssertionError(f'HTTP attempted during test: {request.url}')

    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', _blocked)
    yield attempted
