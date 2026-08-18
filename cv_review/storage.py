"""Persistence helpers: human-friendly (sanitized) filenames, optional Google
Drive organization, and data retention.

Naming principle: candidate names are LABELS for humans; UUIDs are the
security identifiers. Files are addressed internally by review UUID + owner —
the sanitized name only ever appears as a display filename.
"""
import io
import json
import os
import re
from datetime import datetime, timedelta

_UNSAFE = re.compile(r'[/\\:*?"<>|\x00-\x1f\x7f]')
_NON_LABEL = re.compile(r'[^\w.\- ]', re.UNICODE)


def sanitize_name(name):
    """Candidate name → filesystem/Drive-safe label. Removes path separators,
    traversal sequences, null bytes and control/filesystem-sensitive chars;
    keeps unicode letters (Hebrew names are fine as labels)."""
    label = _UNSAFE.sub('', str(name or ''))
    label = _NON_LABEL.sub('', label)
    label = re.sub(r'\s+', '_', label.strip())
    label = label.strip('._-')
    while '..' in label:
        label = label.replace('..', '.')
    return label[:64] or 'Candidate'


def review_filenames(candidate_name):
    safe = sanitize_name(candidate_name)
    return {
        'docx': f'{safe}_CV_Optimized.docx',
        'pdf': f'{safe}_CV_Optimized.pdf',
        'txt': f'{safe}_CV_Optimized.txt',
        'original': f'{safe}_original_untrusted',
    }


# ── Optional Google Drive mirror ─────────────────────────────────────────────
# Structure:  <GOOGLE_DRIVE_CV_FOLDER_ID>/<owner_key>/<review_uuid>/<files>
# The raw original is uploaded with an explicit *_original_untrusted name.
# Permissions are NEVER granted — no public sharing, ownership stays with the
# service account / shared folder ACL.

def _drive():
    creds_env = os.environ.get('GOOGLE_DRIVE_CREDENTIALS_JSON')
    root = os.environ.get('GOOGLE_DRIVE_CV_FOLDER_ID')
    if not creds_env or not root:
        return None, None
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    if creds_env.strip().startswith('{'):
        info = json.loads(creds_env)
    else:
        with open(creds_env, encoding='utf-8') as f:
            info = json.load(f)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=['https://www.googleapis.com/auth/drive'])
    return build('drive', 'v3', credentials=creds, cache_discovery=False), root


def _ensure_folder(svc, name, parent):
    safe = name.replace("'", "\\'")
    res = svc.files().list(
        q=f"name = '{safe}' and '{parent}' in parents and "
          f"mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields='files(id)', pageSize=1, supportsAllDrives=True,
        includeItemsFromAllDrives=True).execute()
    found = res.get('files')
    if found:
        return found[0]['id']
    created = svc.files().create(
        body={'name': name, 'parents': [parent],
              'mimeType': 'application/vnd.google-apps.folder'},
        fields='id', supportsAllDrives=True).execute()
    return created['id']


def upload_review_to_drive(owner_key, review_id, files):
    """files: {filename: (bytes, mime)}. Returns {'folder_id', 'files': {...}}
    or None when Drive isn't configured. Failures are logged, never fatal —
    Postgres remains the durable store (prod's local disk is ephemeral)."""
    try:
        svc, root = _drive()
        if svc is None:
            return None
        from googleapiclient.http import MediaIoBaseUpload
        owner_folder = _ensure_folder(svc, owner_key, root)
        review_folder = _ensure_folder(svc, review_id, owner_folder)
        ids = {}
        for filename, (data, mime) in files.items():
            media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
            created = svc.files().create(
                body={'name': filename, 'parents': [review_folder]},
                media_body=media, fields='id', supportsAllDrives=True).execute()
            ids[filename] = created['id']
        return {'folder_id': review_folder, 'files': ids}
    except Exception as exc:
        print(f'⚠️ CV review: Drive upload skipped ({type(exc).__name__}: {exc})')
        return None


# ── Stale in-flight reviews ──────────────────────────────────────────────────
# A review runs in a background thread, so a deploy or container restart kills
# it mid-flight and leaves the row stuck on 'processing' forever — the client
# would poll until it gives up with a vague message. Anything still
# 'processing' past this window is declared failed, with a message that tells
# the user what to do.
STALE_MINUTES = 6
STALE_MESSAGE = ('The review was interrupted (the server restarted mid-run). '
                 'Please upload your CV again — it usually takes under a minute.')


def fail_stale_processing():
    from database.models import db, CvReview
    cutoff = datetime.utcnow() - timedelta(minutes=STALE_MINUTES)
    try:
        n = (CvReview.query
             .filter(CvReview.status == 'processing', CvReview.created_at < cutoff)
             .update({'status': 'failed', 'error': STALE_MESSAGE},
                     synchronize_session=False))
        db.session.commit()
        if n:
            print(f'⚠️ CV review: {n} interrupted review(s) marked failed')
        return n
    except Exception as exc:
        db.session.rollback()
        print(f'⚠️ CV review: stale sweep failed ({exc})')
        return 0


def is_stale(review):
    return (review.status == 'processing' and review.created_at
            and review.created_at < datetime.utcnow() - timedelta(minutes=STALE_MINUTES))


# ── Retention ────────────────────────────────────────────────────────────────
def purge_expired():
    """Data retention, run opportunistically on new-review creation.
    Two tiers (consent to keep the CV is REQUIRED to run a review, so consent
    alone no longer distinguishes rows):
      * failed / never-completed runs: purged after 7 days — they hold an
        original CV that never delivered value.
      * completed reviews WITHOUT talent-pool consent (legacy rows from before
        consent became mandatory): purged after CV_REVIEW_RETENTION_DAYS.
    Completed + consented reviews are kept until a deletion request."""
    from database.models import db, CvReview
    now = datetime.utcnow()
    days = int(os.environ.get('CV_REVIEW_RETENTION_DAYS', '180'))
    try:
        n = (CvReview.query
             .filter(CvReview.status != 'complete',
                     CvReview.created_at < now - timedelta(days=7))
             .delete(synchronize_session=False))
        if days > 0:
            n += (CvReview.query
                  .filter(CvReview.status == 'complete',
                          CvReview.talent_pool_consent.is_(False),
                          CvReview.created_at < now - timedelta(days=days))
                  .delete(synchronize_session=False))
        db.session.commit()
        if n:
            print(f'🧹 CV review: purged {n} expired review(s)')
        return n
    except Exception as exc:
        db.session.rollback()
        print(f'⚠️ CV review: retention purge failed ({exc})')
        return 0
