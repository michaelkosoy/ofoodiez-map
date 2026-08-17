"""Isolated execution of the untrusted-document parser.

Isolation model — chosen for the actual deployment (a Render web service and
local dev, where no Docker daemon is available and mounting /var/run/docker.sock
is forbidden anyway): every uploaded DOCX is parsed by a ONE-SHOT child Python
process that

  * receives a SCRUBBED environment — no GEMINI_API_KEY, no DATABASE_URL, no
    SECRET_KEY, no Drive credentials, no application variables at all (only
    PATH/HOME/locale). A parser exploit therefore lands in a process that
    holds no secrets and no DB access.
  * runs under hard rlimits: address-space, CPU seconds, written-file size,
    open files, core dumps off, process count (Linux).
  * is killed on a wall-clock timeout (start_new_session=True so the whole
    process group dies).
  * executes stdlib-only code (cv_review/docx_worker.py) that performs no
    network I/O and rejects XML DTDs/entities, so there is no fetch vector.

Upgrade path if the deployment ever moves to Docker/K8s: run the same worker
in a dedicated container with non-root user, cap_drop ALL, no-new-privileges,
read-only rootfs + tmpfs, seccomp default, network=none. The protocol
(input file -> JSON verdict) stays identical.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

WORKER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docx_worker.py')

PARSE_TIMEOUT_SECONDS = 20
_RLIMIT_AS_BYTES = 768 * 1024 * 1024   # interpreter + 20MB part + slack
_RLIMIT_CPU_SECONDS = 15
_RLIMIT_FSIZE_BYTES = 64 * 1024 * 1024
_RLIMIT_NOFILE = 64


def scrubbed_env(home):
    """The ENTIRE environment the parser child receives. Never os.environ."""
    return {
        'PATH': '/usr/bin:/bin',
        'HOME': home,
        'LC_ALL': 'C.UTF-8',
        'PYTHONIOENCODING': 'utf-8',
        'PYTHONDONTWRITEBYTECODE': '1',
    }


def _apply_rlimits():
    import resource
    try:
        resource.setrlimit(resource.RLIMIT_AS, (_RLIMIT_AS_BYTES, _RLIMIT_AS_BYTES))
    except ValueError:
        if sys.platform.startswith('linux'):
            raise
        # macOS can't always lower RLIMIT_AS (and doesn't enforce it anyway);
        # best-effort there — Linux (production) stays strict.
        try:
            resource.setrlimit(resource.RLIMIT_AS,
                               (_RLIMIT_AS_BYTES, resource.RLIM_INFINITY))
        except ValueError:
            pass
    resource.setrlimit(resource.RLIMIT_CPU, (_RLIMIT_CPU_SECONDS, _RLIMIT_CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (_RLIMIT_FSIZE_BYTES, _RLIMIT_FSIZE_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (_RLIMIT_NOFILE, _RLIMIT_NOFILE))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if sys.platform.startswith('linux'):
        # On macOS RLIMIT_NPROC counts the user's whole session — Linux only.
        resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))


def run_isolated_script(script_path, args, timeout=PARSE_TIMEOUT_SECONDS, workdir=None):
    """Run `python script_path *args` in the scrubbed/limited child.

    Returns (returncode, stdout, stderr). Raises subprocess.TimeoutExpired.
    Exposed separately so tests can push probe scripts through the exact same
    boundary the production parser uses."""
    own_dir = workdir is None
    if own_dir:
        workdir = tempfile.mkdtemp(prefix='cvsandbox-')
    try:
        proc = subprocess.run(
            [sys.executable, script_path, *args],
            cwd=workdir, env=scrubbed_env(workdir),
            capture_output=True, timeout=timeout,
            start_new_session=True, preexec_fn=_apply_rlimits,
        )
        return proc.returncode, proc.stdout, proc.stderr
    finally:
        if own_dir:
            shutil.rmtree(workdir, ignore_errors=True)


def parse_docx(file_bytes, timeout=PARSE_TIMEOUT_SECONDS):
    """Parse untrusted .docx bytes in the sandbox.

    Returns the worker's JSON verdict:
      {'ok': True, 'text': ..., 'meta': ...} or
      {'ok': False, 'error_code': ..., 'message': <safe user-facing text>}.
    Never raises for hostile input; never leaks stack traces to the caller."""
    workdir = tempfile.mkdtemp(prefix='cvparse-')
    in_path = os.path.join(workdir, 'input.docx')
    out_path = os.path.join(workdir, 'verdict.json')
    try:
        with open(in_path, 'wb') as f:
            f.write(file_bytes)
        os.chmod(in_path, 0o600)
        try:
            rc, _out, err = run_isolated_script(
                WORKER_PATH, [in_path, out_path], timeout=timeout, workdir=workdir)
        except subprocess.TimeoutExpired:
            print('❌ docx sandbox: parse timeout — job killed')
            return {'ok': False, 'error_code': 'timeout',
                    'message': 'This document took too long to read and was rejected.'}
        if rc != 0:
            # Crash under rlimits (e.g. MemoryError) — log server-side only.
            print(f'❌ docx sandbox: worker exited {rc}: {err[-500:] if err else b""}')
            return {'ok': False, 'error_code': 'parse_failed',
                    'message': 'Could not read this document. Please try a different file.'}
        try:
            with open(out_path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            print('❌ docx sandbox: worker produced no verdict')
            return {'ok': False, 'error_code': 'parse_failed',
                    'message': 'Could not read this document. Please try a different file.'}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
