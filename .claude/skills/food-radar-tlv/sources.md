# Sources — food-radar-tlv

Search **all** categories every run, in **Hebrew and English**. Prefer Tavily Search/Extract for
discovery and Tavily Crawl/Map for the known high-value pages listed under "Crawl/Map targets".

> URLs below are entry points / patterns, not guaranteed-stable deep links. Always confirm a real,
> reachable proof URL via an actual tool result before using it. Never invent or autocomplete a URL.

---

## 1. Israeli food / news / media

| Source | Notes | Entry point |
|--------|-------|-------------|
| Time Out Tel Aviv / Israel | Food & restaurant news, openings | https://www.timeout.co.il/ |
| Mako — Food / Mako Eats | Restaurant news, openings, chef items | https://www.mako.co.il/food |
| Ynet — food | Restaurant & culinary news | https://www.ynet.co.il/food |
| Walla — food | Restaurant news | https://food.walla.co.il/ |
| Haaretz — food | Use only if accessible (paywall — do not bypass) | https://www.haaretz.co.il/food |
| Secret Tel Aviv | EN community: openings, pop-ups, events | https://secrettelaviv.com/ |
| Debbest Food | Restaurant-opening coverage | https://debbestfood.com/ |
| Local food blogs | HE food bloggers, openings roundups | discover via Tavily Search |
| Local newsletters | City / food newsletters | discover via Tavily Search |
| Local event calendars | Culinary events, pop-ups | discover via Tavily Search |

## 2. Reservation / listing platforms

| Source | Look for | Entry point |
|--------|----------|-------------|
| Ontopo | New venue pages, new reservation pages, pop-up reservations | https://ontopo.com/he/il |
| Tabit | New listings, event pages, "coming soon" | https://www.tabitisrael.co.il/ |
| Google Maps / Google Business | Newly listed places, "opening soon", changed hours, new menus | public results via Tavily/WebSearch |
| Israeli local business listings | New listings (if accessible) | discover via Tavily Search |
| Restaurant websites / menu pages | New menus, new locations, soft-opening notes | discover via Tavily Search |
| Event pages | Pop-up reservation pages, one-off dinners | discover via Tavily/Facebook events |

Signals to watch on these platforms: new venue page · new reservation page · event page · "coming
soon" · soft opening · newly listed place · new menu · changed opening hours · pop-up reservation page.

## 3. Public *indexed* social signals

Use **Tavily indexed search only** (do not log in / scrape private data). Targets:
Instagram · TikTok · Facebook public pages & events · LinkedIn public hiring posts · public creator
pages · public restaurant/chef pages. Account/hashtag/keyword seeds: `social-watchlist.yaml`.
Query patterns: `search-queries.md` group E.

## 4. Hiring / opening signals

Hiring posts often precede an opening by weeks. Search HE + EN "now hiring for a new place" phrasing
(`search-queries.md` group C). Sources: LinkedIn public posts, Facebook groups (public), Israeli job
boards (public), restaurant career pages. Treat as early signal → verify the venue (§6 of `SKILL.md`).

---

## Crawl / Map targets (known public pages where new items appear)

Use Tavily **Crawl** to read these for new items, and Tavily **Map** when you need the list of newly
added URLs under a section. Be economical and respect robots.

- **Time Out Tel Aviv** — food / restaurant-news section pages
- **Mako** — food / restaurant-news pages
- **Ontopo Tel Aviv** — listing / category pages
- **Tabit Israel** — listing / event pages
- **Secret Tel Aviv** — event / food pages
- **Debbest Food** — restaurant-opening pages
- **Public event calendars** — culinary events & pop-ups

**Map is most useful for:** reservation-platform category pages · event pages · food-news archives ·
restaurant category pages — i.e. sources with many pages where you need only the *newly added* URLs.

---

## Mandatory every-run reservation checks (Ontopo + Tabit — never skip either)

On **every** run you must hit **both** platforms (see `SKILL.md` §5 / §15 step 6). Reservation pages
rarely expose a "date added", so use them as **discovery + corroboration**: a new or newly-bookable
page is a strong signal even with no media coverage, and pulling a reservation link for a venue you
found elsewhere raises its confidence.

**Ontopo** — `tavily_map` the category pages, then `tavily_search` (`include_domains: ["ontopo.com"]`):
- https://ontopo.com/he/il/tel-aviv  (all TLV) · …/tel-aviv/bars · …/tel-aviv/chef-restaurants
- https://ontopo.com/he/il  → region pages: אזור המרכז / השרון / רמת גן-גבעתיים / הרצליה / כפר סבא, etc.
- Search the run's candidate names (e.g. a place just seen on Mako/Time Out) to find its booking page.

**Tabit** — `tavily_search` (`include_domains: ["tabitisrael.co.il","tabit.cloud","tabit.rest"]`):
- https://tabitisrael.co.il  (home / new listings) · /site/<venue> venue pages · /online-reservations/…
- Query "מסעדה חדשה / בר חדש / הזמנת שולחן תל אביב" + the run's candidate names.

**If a platform returns nothing usable**, say so in the run notes — do not silently skip it. Log
undated finds as `watch` records in `seen-records.json` so a later run can promote them once dated.
