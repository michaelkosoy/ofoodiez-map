"""Generic "public submits a business listing -> admin approves/rejects" machinery,
shared by any page that lists categorized entries (places/suppliers for the
bachelorette guide, vendors for the HiTech directory). Adding a new page is meant
to be just a new entry in LISTING_SUBMISSION_CONFIGS plus matching seed arrays in
that page's blog_<slug>.json -- app.py's submit route and admin/api.py's
approve/reject route are both slug-driven and don't need new code per page.

The entries themselves live in the `listing_entries` DB table, not in the JSON
file -- see § Storage at the bottom for why and for the read/write helpers.
"""
import os
import json
import tempfile
from datetime import datetime

# slug -> {
#   'kinds': {kind_key: {'array_key': ..., 'label_he': ..., 'categories': [...]}},
#   'listing_title_he': shown in admin notification emails,
#   'listing_url': shown in admin/approval emails,
# }
LISTING_SUBMISSION_CONFIGS = {
    'bachelorette': {
        'kinds': {
            'venue': {
                'array_key': 'places',
                'label_he': 'מקום/חלל',
                'categories': ["חלל ושף", "יקבים", "חלל פרטי להשכרה", "חדר פרטי במסעדה"],
            },
            'supplier': {
                'array_key': 'suppliers',
                'label_he': 'ספק',
                'categories': ["דיג׳יי", "שף פרטי", "אטרקציה", "בר אלכוהול", "אחר"],
            },
        },
        'listing_title_he': 'מדריך הרווקות',
        'listing_url': 'https://ofoodiez.com/blog/bachelorette',
    },
    # Career-service providers for the HiTech section. Slug is decoupled from the
    # URL (this page lives at /hitech/suppliers, not /blog/) — blog_json_path just
    # maps it to app/data/blog_hitech_suppliers.json.
    'hitech_suppliers': {
        'kinds': {
            'supplier': {
                'array_key': 'suppliers',
                'label_he': 'Vendor',
                'categories': ["Happy Hours", "Career Mentors", "Other"],
            },
        },
        'listing_title_he': 'Vendors in Tech',
        'listing_url': 'https://ofoodiez.com/hitech/suppliers',
    },
}


def get_config(slug):
    return LISTING_SUBMISSION_CONFIGS.get(slug)


def blog_json_path(slug):
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'app', 'data', f'blog_{slug}.json')


def atomic_write_json(path, data):
    """Write via a temp file + os.replace so a concurrent reader (another public
    submission, or the admin panel's bulk save, writing the same file) never sees
    a truncated/partial file -- plain open(path, 'w') truncates before writing,
    which is unsafe once more than one process can write this file."""
    dir_name = os.path.dirname(path) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def is_listing_approved(entry):
    """Submitted entries carry a status ('pending'/'approved'/'needs_editing'/'rejected');
    hand-curated entries have no status field at all and are implicitly approved."""
    return entry.get('status', 'approved') == 'approved'


def filter_approved(blog_data, config):
    """Return a copy of blog_data with every kind's array filtered to approved-only
    (for public rendering) -- leaves everything else in blog_data untouched."""
    filtered = dict(blog_data)
    for kind_config in config['kinds'].values():
        array_key = kind_config['array_key']
        filtered[array_key] = [e for e in filtered.get(array_key, []) if is_listing_approved(e)]
    return filtered


# ── Storage ────────────────────────────────────────────────────────────────────
# The entries live in the DB (database.models.ListingEntry), NOT in the page's
# blog_<slug>.json: the public form and the admin grid both write them in
# production, where the filesystem is ephemeral and a file write is erased by the
# next deploy or restart. The JSON file holds the page's static copy (intro,
# games, designs, gifts -- edited in git) plus the one-time seed arrays.

def _kinds(slug):
    return LISTING_SUBMISSION_CONFIGS[slug]['kinds']


def entry_arrays(slug):
    """{array_key: [entry dicts]} for every kind of `slug`, in display order."""
    from database.models import ListingEntry

    array_key_of = {kind: c['array_key'] for kind, c in _kinds(slug).items()}
    arrays = {key: [] for key in array_key_of.values()}
    rows = (ListingEntry.query.filter_by(slug=slug)
            .order_by(ListingEntry.position, ListingEntry.id).all())
    for row in rows:
        array_key = array_key_of.get(row.kind)
        if array_key:
            arrays[array_key].append(dict(row.data or {}))
    return arrays


def merge_entries(blog_data, slug):
    """Copy of blog_data with each kind's array replaced by the DB rows -- the
    read path for both the public page and the admin grid."""
    merged = dict(blog_data)
    merged.update(entry_arrays(slug))
    return merged


def replace_entries(slug, kind, entries):
    """Whole-array save: the admin grid PUTs the full list, so rewrite this kind's
    rows in the submitted order. A row deleted in the grid is deleted here."""
    from database.models import db, ListingEntry

    ListingEntry.query.filter_by(slug=slug, kind=kind).delete()
    for position, entry in enumerate(entries):
        data = {k: v for k, v in entry.items() if k != 'id'}  # 'id' is the grid's cosmetic row number
        db.session.add(ListingEntry(slug=slug, kind=kind, position=position, data=data))
    db.session.commit()


def add_entry(slug, kind, entry):
    """Append one entry -- the public submission form's write path."""
    from database.models import db, ListingEntry

    last = (db.session.query(db.func.max(ListingEntry.position))
            .filter(ListingEntry.slug == slug, ListingEntry.kind == kind).scalar())
    db.session.add(ListingEntry(slug=slug, kind=kind, position=(last or 0) + 1, data=entry))
    db.session.commit()


def set_entry_status(slug, kind, submission_id, status):
    """Approve/reject one submitted entry. Returns the updated entry dict, or None
    if no entry carries that submission_id."""
    from database.models import db, ListingEntry

    rows = ListingEntry.query.filter_by(slug=slug, kind=kind).all()
    row = next((r for r in rows if (r.data or {}).get('submission_id') == submission_id), None)
    if not row:
        return None
    entry = dict(row.data or {})
    entry['status'] = status
    entry['reviewed_at'] = datetime.utcnow().isoformat()
    row.data = entry   # reassign, don't mutate: a JSON column doesn't track in-place edits
    db.session.commit()
    return entry


def seed_entries(slug):
    """One-time import of a page's entries from blog_<slug>.json into the DB.

    ponytail: guarded on "this slug has no rows at all", not per kind, so clearing
    out one kind (e.g. all suppliers) isn't undone on the next restart. Emptying
    *every* row of a page does re-seed it from the file, which is the recovery
    path anyway -- drop the arrays from the JSON if you want a page to stay empty.
    """
    from database.models import db, ListingEntry

    if db.session.query(ListingEntry.id).filter(ListingEntry.slug == slug).first():
        return
    path = blog_json_path(slug)
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as f:
        blog_data = json.load(f)
    for kind, kind_config in _kinds(slug).items():
        for position, entry in enumerate(blog_data.get(kind_config['array_key'], [])):
            db.session.add(ListingEntry(slug=slug, kind=kind, position=position, data=entry))
    db.session.commit()
