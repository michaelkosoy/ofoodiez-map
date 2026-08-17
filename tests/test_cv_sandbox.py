"""Isolation-boundary proofs (§ parser must not see application secrets)."""
import os
import subprocess
import sys
import textwrap

import pytest

from cv_review import sandbox
import cv_evil_docs as evil

PROBE = textwrap.dedent("""
    import json, os, sys
    print(json.dumps({
        'env_keys': sorted(os.environ.keys()),
        'docker_host': os.environ.get('DOCKER_HOST'),
        'docker_sock': os.path.exists('/var/run/docker.sock'),
    }))
""")

SECRETS = {
    'GEMINI_API_KEY': 'fake-gemini-secret',
    'DATABASE_URL': 'postgresql://fake',
    'SECRET_KEY': 'fake-session-secret',
    'GOOGLE_DRIVE_CREDENTIALS_JSON': '{"fake": true}',
    'ADMIN_SECRET': 'fake-admin',
    'DOCKER_HOST': 'unix:///var/run/docker.sock',
}


def test_worker_env_has_no_secrets(tmp_path, monkeypatch):
    """The parser child must not inherit ANY application/cloud secret from the
    web process, and must have no Docker access configured."""
    for key, value in SECRETS.items():
        monkeypatch.setenv(key, value)
    probe = tmp_path / 'probe.py'
    probe.write_text(PROBE)
    rc, out, err = sandbox.run_isolated_script(str(probe), [], timeout=15)
    assert rc == 0, err
    import json
    report = json.loads(out)
    for key in SECRETS:
        assert key not in report['env_keys'], f'{key} leaked into parser env'
    assert report['docker_host'] is None
    # Whole env is exactly the scrubbed allowlist — nothing else.
    assert set(report['env_keys']) <= {'PATH', 'HOME', 'LC_ALL',
                                       'PYTHONIOENCODING', 'PYTHONDONTWRITEBYTECODE',
                                       'LC_CTYPE', '__CF_USER_TEXT_ENCODING'}
    if sys.platform.startswith('linux'):
        assert not report['docker_sock'], 'Docker socket reachable from parser'


def test_worker_parses_docx_through_sandbox():
    out = sandbox.parse_docx(evil.good_docx())
    assert out['ok'] and 'Jane Smith' in out['text']


def test_evil_docx_through_sandbox_is_safe_error():
    out = sandbox.parse_docx(evil.vba_project_docx())
    assert out == {'ok': False, 'error_code': 'macros',
                   'message': 'Macro-enabled documents are not supported. '
                              'Please upload a plain .docx.'}


def test_timeout_kills_worker(tmp_path):
    hang = tmp_path / 'hang.py'
    hang.write_text('import time\ntime.sleep(60)\n')
    with pytest.raises(subprocess.TimeoutExpired):
        sandbox.run_isolated_script(str(hang), [], timeout=2)


def test_parse_timeout_returns_safe_error(tmp_path, monkeypatch):
    hang = tmp_path / 'hang.py'
    hang.write_text('import sys, time\ntime.sleep(60)\n')
    monkeypatch.setattr(sandbox, 'WORKER_PATH', str(hang))
    out = sandbox.parse_docx(b'PK\x03\x04', timeout=2)
    assert out['ok'] is False and out['error_code'] == 'timeout'


def test_worker_crash_returns_generic_error_no_traceback(tmp_path, monkeypatch):
    boom = tmp_path / 'boom.py'
    boom.write_text('raise RuntimeError("kaboom secret-detail")\n')
    monkeypatch.setattr(sandbox, 'WORKER_PATH', str(boom))
    out = sandbox.parse_docx(b'PK\x03\x04')
    assert out['ok'] is False and out['error_code'] == 'parse_failed'
    assert 'kaboom' not in out['message'] and 'Traceback' not in out['message']


@pytest.mark.skipif(not sys.platform.startswith('linux'),
                    reason='RLIMIT_AS is only reliably enforced on Linux')
def test_memory_limit_enforced(tmp_path):
    hog = tmp_path / 'hog.py'
    hog.write_text('x = bytearray(2 * 1024 * 1024 * 1024)\nprint("allocated")\n')
    rc, out, _err = sandbox.run_isolated_script(str(hog), [], timeout=15)
    assert rc != 0 and b'allocated' not in out
