# Project Overview — Ofoodiez

## What this is
A Flask web app and food blog. Main features:
- **Happy Hour Map** — Google Maps–based map of Tel Aviv bars/restaurants with happy hour info
- **Blog** — travel guides and food content (Japan guide, Bachelorette, Instagram feed)
- **Pop-ups Calendar** — upcoming food events in Tel Aviv
- **HiTech Community** — waitlist/signup page for a tech community
- **Admin Panel** — internal tool to manage places, events, blog content, users

## Stack
- **Backend**: Python / Flask (`app.py` is the entry point)
- **Templates**: Jinja2 (`app/templates/`)
- **Styles**: Plain CSS (`app/static/css/`)
- **Data**: PostgreSQL (prod) via SQLAlchemy; JSON files for blog content (`app/data/`)
- **Deployment**: Gunicorn (`Procfile`), likely Render or Railway
- **Maps**: Google Maps JS API (key in env var `GOOGLE_MAPS_API_KEY`)

## Key files
| File | Purpose |
|------|---------|
| `app.py` | All routes and app setup |
| `data.py` | Static data (world maps carousel, home page content) |
| `app/data/blog_japan.json` | Editable text for Japan blog (loaded via `_load_blog('japan')`) |
| `app/templates/home.html` | Home page |
| `app/templates/components/blog_menu.html` | Blog nav pills (included on every page) |
| `app/templates/components/bottom_nav.html` | Mobile bottom nav |
| `admin/routes.py` | Admin panel page routes |
| `admin/api.py` | Admin panel API endpoints |

## Environment variables needed
- `GOOGLE_MAPS_API_KEY`
- `DATABASE_URL` (PostgreSQL)
- Any email/SMTP credentials for notifications
- `GROW_MAKE_WEBHOOK_URL` — Make scenario webhook that runs Grow's Create Payment Link module and replies with the payment URL; enables automatic per-user payment links + auto-unlock for the Japan guide (`billing.py`). The Grow↔Make connection is phone-verified — merchants get no API key of their own, so Make is the normal transport.
- `GROW_API_KEY`, `GROW_USER_ID`, `GROW_PAGE_CODE`, `GROW_API_BASE` — direct Grow Light API access (same effect as the Make webhook; only if Grow support issues credentials). Without either transport the guide falls back to the static link + manual activation.
- `GROW_JAPAN_PAY_LINK` — the Japan guide's public Grow payment-page URL (has a default in `billing.py`). Item price **and name** are managed **in the Grow dashboard only**: the site reads them live from each item's page (`grow_page_item()`), shows the price on the locked page, and charges it at checkout. Never hardcode prices. All sellable items live in `billing.GROW_ITEMS` (slug → page_url/catalog/path); per-user purchases in the `site_purchases` table. See docs/ai/blog-pages.md § Paid (gated) pages.

## Private portfolio (/portfolio)
`/portfolio` is gated: clients unlock it with a per-company access code (created in
admin → Portfolio Access, `portfolio_access` table, valid 7 days, renewable) or with
`ADMIN_SECRET`. `/portfolio/lock` re-locks the current browser (gate preview). Grants are
re-checked in the DB per visit, so deleting a code revokes access. The locked screen is
`app/templates/portfolio_gate.html` (terminal-boot design); its copy lives in
`portfolio_content.json` under `portfolio.gate` (editable at /admin/portfolio/content).

## Content conventions — text must be editable, not hardcoded
Any user-facing copy added to the site (headlines, button labels, descriptions, FAQ
entries, etc.) must live in an editable JSON content file under `app/data/`, not
hardcoded as literal strings in the Jinja templates. This keeps every page editable
from the admin panel, and sets the site up for an eventual translation/i18n feature
(swap one JSON file for a per-locale one) without touching template code.

Follow the existing pattern used for the HiTech pages:
- **Data file**: `app/data/hitech_content.json`, keyed by page (`hitech`, `community`,
  `bot`, `cv`). Loaded via `_load_hitech_content()` in `app.py` and passed to templates
  as `c`, e.g. `{{ c.headline }}`. Always reference copy through `c.<key>`, never inline
  text, and give new keys a sensible fallback with `| default('...')` in the template.
- **Admin editor**: `app/templates/admin/hitech_content.html` + the GET/PUT endpoints at
  `/admin/api/hitech/content` (`admin/api.py`) — a generic "load JSON → render form
  fields → save whole JSON back" editor keyed by section. When adding a new field or
  repeatable list (cards, steps, FAQ items) to a page, add the matching form field(s) to
  this editor's `renderEditor()`/`collectData()` so it stays editable from
  `/admin/hitech/content`. Variable-length lists (like FAQ) should support add/remove,
  not just a fixed set of fields.
- Non-HiTech pages that grow admin-editable copy should follow the same shape: one JSON
  file per page/section in `app/data/`, one admin editor page + API pair to read/write it.

## Do not do
- Do not push large images (>500KB) directly to the git repo — it can break the production deployment
- Do not create blog pages outside `/blog/` prefix
- Do not add routes after the `/blog/<category>` catch-all — they won't be reached
- Do not hardcode new user-facing text directly in templates — add it to the relevant
  JSON content file and expose it in the matching admin editor (see "Content conventions" above)
