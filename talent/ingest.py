"""Gmail CV ingestion over IMAP (stdlib imaplib + email).

Read-only mailbox access with an app password (TALENT_GMAIL_USER /
TALENT_GMAIL_APP_PASSWORD). Sync is idempotent: emails dedupe on Message-ID,
so running it any number of times ingests each CV email once. Gmail is ONLY
an ingestion source — all state lives in the dashboard DB (§38).
"""
import email
import email.header
import email.utils
import imaplib
import logging
import re
from datetime import datetime, timedelta, timezone

from database.models import db

from . import config
from .models import TalentEmail
from .pipeline import UploadError, add_cv, ensure_candidate

logger = logging.getLogger('talent')

_CV_NAME_HINT = re.compile(r'cv|resume|קורות', re.IGNORECASE)


def _decode(value):
    if not value:
        return ''
    try:
        return str(email.header.make_header(email.header.decode_header(value)))
    except Exception:
        return value


def _received_at(msg):
    try:
        dt = email.utils.parsedate_to_datetime(msg.get('Date'))
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return datetime.utcnow()


def _body_snippet(msg, limit=800):
    for part in msg.walk():
        if part.get_content_type() == 'text/plain' and not part.get_filename():
            try:
                payload = part.get_payload(decode=True) or b''
                text = payload.decode(part.get_content_charset() or 'utf-8', 'replace')
                return re.sub(r'\n{3,}', '\n\n', text.strip())[:limit]
            except Exception:
                return ''
    return ''


def _cv_attachments(msg):
    """(filename, bytes) for every PDF/DOCX part, CV-looking names first."""
    found = []
    for part in msg.walk():
        filename = _decode(part.get_filename())
        if not filename:
            continue
        ext = ('.' + filename.rsplit('.', 1)[-1].lower()) if '.' in filename else ''
        if ext not in config.ALLOWED_EXTS:
            continue
        payload = part.get_payload(decode=True)
        if payload:
            found.append((filename, payload))
    found.sort(key=lambda t: 0 if _CV_NAME_HINT.search(t[0]) else 1)
    return found


def sync_gmail():
    """Pull recent inbox emails, ingest new CV emails, return a summary dict.
    Fast (no AI) — the caller kicks off background analysis afterwards."""
    cfg = config.gmail_config()
    if not cfg['user'] or not cfg['password']:
        return {'ok': False,
                'error': 'Gmail sync is not configured — set TALENT_GMAIL_USER '
                         'and TALENT_GMAIL_APP_PASSWORD.'}
    try:
        box = imaplib.IMAP4_SSL('imap.gmail.com', timeout=30)
        box.login(cfg['user'], cfg['password'])
        box.select(f'"{cfg["folder"]}"', readonly=True)
        # %d-%b-%Y needs English month names — fine on the C/C.UTF-8 locales
        # this app runs under (local mac + Render).
        since = (datetime.utcnow() - timedelta(days=cfg['days'])).strftime('%d-%b-%Y')
        _typ, data = box.uid('SEARCH', f'(SINCE {since})')
    except (imaplib.IMAP4.error, OSError) as exc:
        return {'ok': False, 'error': f'Gmail connection failed: {exc}'}

    uids = [u.decode() for u in data[0].split()] if data and data[0] else []
    summary = {'ok': True, 'scanned': len(uids), 'new_emails': 0,
               'new_candidates': 0, 'new_cvs': 0, 'skipped': 0}
    if not uids:
        box.logout()
        return summary

    # Batched header fetches (chunked to keep the command line sane), then one
    # IN-query dedupe — never a DB query or IMAP round-trip per message.
    uid_msgid = []
    for i in range(0, len(uids), 200):
        _typ, resp = box.uid('FETCH', ','.join(uids[i:i + 200]),
                             '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])')
        for item in resp or []:
            if not isinstance(item, tuple):
                continue
            m = re.search(rb'UID (\d+)', item[0])
            if not m:
                continue
            uid = m.group(1).decode()
            hdr = email.message_from_bytes(item[1])
            msgid = (hdr.get('Message-ID') or '').strip()[:512]
            uid_msgid.append((uid, msgid or f'<synthetic-uid-{uid}@talent-sync>'))

    known = set()
    all_ids = [mid for _, mid in uid_msgid]
    for i in range(0, len(all_ids), 500):
        chunk = all_ids[i:i + 500]
        known.update(mid for (mid,) in db.session.query(TalentEmail.message_id)
                     .filter(TalentEmail.message_id.in_(chunk)).all())

    for uid, msgid in uid_msgid:
        if msgid in known:
            continue
        try:
            _typ, full = box.uid('FETCH', uid, '(BODY.PEEK[])')
            raw = next(item[1] for item in full if isinstance(item, tuple))
            msg = email.message_from_bytes(raw)
        except Exception as exc:
            logger.warning('talent sync: fetch uid %s failed: %s', uid, exc)
            continue

        from_name, from_email = email.utils.parseaddr(msg.get('From', ''))
        from_name = _decode(from_name)[:256]
        from_email = (from_email or '').lower()[:256]
        if from_email == cfg['user'].lower():
            continue  # my own outbound mail is not a candidate
        attachments = _cv_attachments(msg)
        if not attachments:
            summary['skipped'] += 1
            continue

        row = TalentEmail(message_id=msgid, from_name=from_name,
                          from_email=from_email, subject=_decode(msg.get('Subject'))[:1000],
                          snippet=_body_snippet(msg), received_at=_received_at(msg))
        db.session.add(row)
        db.session.flush()

        cand, was_new = ensure_candidate(email=from_email, name=from_name,
                                         source='EMAIL')
        cv_added = False
        for filename, payload in attachments:
            try:
                add_cv(cand, payload, filename, email_id=row.id)
                cv_added = True
                break  # first valid CV-looking attachment wins
            except UploadError as exc:
                logger.info('talent sync: attachment %r rejected: %s', filename, exc)
        if not cv_added:
            db.session.delete(row)
            if was_new:
                db.session.delete(cand)  # no CV survived -> no empty card
            db.session.commit()
            summary['skipped'] += 1
            continue
        row.candidate_id = cand.id
        db.session.commit()
        summary['new_emails'] += 1
        summary['new_cvs'] += 1
        if was_new:
            summary['new_candidates'] += 1
        known.add(msgid)

    try:
        box.logout()
    except Exception:
        pass
    return summary
