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
