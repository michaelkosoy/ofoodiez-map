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
- `GROW_API_KEY`, `GROW_USER_ID`, `GROW_PAGE_CODE` — Grow (Meshulam) Light API; enables automatic per-user payment links + auto-unlock for the Japan guide (`billing.py`). Without them the guide falls back to the static link + manual activation.
- `GROW_API_BASE` — Light API base URL (default: Grow sandbox; set the production base to go live)
- `GROW_GUIDE_PRICE` — guide price in ILS (default 1, matching the sandbox catalog item)

## Do not do
- Do not push large images (>500KB) directly to the git repo — it can break the production deployment
- Do not create blog pages outside `/blog/` prefix
- Do not add routes after the `/blog/<category>` catch-all — they won't be reached
