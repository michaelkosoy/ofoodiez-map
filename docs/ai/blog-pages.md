# Blog Pages

## URL convention
All blog pages live under `/blog/<slug>`. Never create a blog page at a top-level URL.

## Existing pages
| URL | Template | Route function |
|-----|----------|----------------|
| `/blog/japan` | `app/templates/blog_japan.html` | `blog_japan()` |
| `/blog/instagram` | `app/templates/blog_instagram.html` | `blog_instagram()` |
| `/blog/bachelorette` | `app/templates/bachelorette.html` | `bachelorette_page()` |

## Catch-all
`/blog/<category>` redirects to `/` (home). Any new blog page MUST have an explicit route defined **before** this catch-all in `app.py`.

## Adding a new blog page — checklist
1. Create `app/templates/blog_<slug>.html`
2. Add `@app.route('/blog/<slug>')` in `app.py` **before** the `blog_category` catch-all route (line ~261)
3. Add the nav pill link in `app/templates/components/blog_menu.html`
4. If the old URL exists at a top-level (e.g. `/<slug>`), add a 301 redirect to `/blog/<slug>`
5. Update this file

## Page structure
Every blog page must include:
```html
{% set active_page = '<slug>' %}
{% include 'components/blog_menu.html' %}
...
{% include 'components/bottom_nav.html' %}
```

## Blog nav pills
Defined in `app/templates/components/blog_menu.html`.
The `active_page` variable controls which pill is highlighted.
Use the slug string (e.g. `'japan'`, `'instagram'`, `'bachelorette'`).
