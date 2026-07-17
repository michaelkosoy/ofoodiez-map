"""Generic "public submits a business listing -> admin approves/rejects" machinery,
shared by any blog page that lists categorized entries in its own blog_<slug>.json
(places/suppliers for the bachelorette guide today; e.g. a future HiTech "find a
supplier" directory tomorrow). Adding a new page is meant to be just a new entry
in LISTING_SUBMISSION_CONFIGS plus matching arrays in that page's blog_<slug>.json
-- app.py's submit route and admin/api.py's approve/reject route are both
slug-driven and don't need new code per page.
"""
import os
import json
import tempfile

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
                'label_he': 'ספק',
                'categories': ["כתיבת קורות חיים", "ליווי קריירה", "הכנה לראיונות",
                               "מנטורינג", "קורסים ובוטקאמפים", "לינקדאין ופורטפוליו", "אחר"],
            },
        },
        'listing_title_he': 'ספקי הקריירה בהייטק',
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
