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

## Paid (gated) pages — sold as Grow items
A page sold as a one-time Grow purchase (like `/blog/japan`) additionally needs ONE
registry entry in `billing.GROW_ITEMS` (slug → the item's public pay.grow.link page URL,
its Grow catalog number, and the page path), and its route starts with:
```python
gate = item_gate('<slug>', title='...', desc='...')   # from billing
if gate:
    return gate
```
Everything else is automatic: price/name are read live from the Grow item, checkout is a
per-user payment link, and the `/webhooks/grow` callback grants the purchase (row in
`site_purchases`). Admin can view/edit per-user items in the Members grid ("Items" column).

Alternatively, give the item a public **landing/sales page** instead of the plain locked
page (what `/blog/japan` does with `blog_japan_landing.html`): the route renders the guide
for owners and the landing for everyone else; the landing CTA is a plain link to
`GET /pay/<slug>` — anonymous clickers are sent to sign up first and the purchase resumes
automatically after auth (`next_after_auth`).

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
