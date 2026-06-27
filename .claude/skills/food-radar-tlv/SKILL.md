---
name: food-radar-tlv
description: Use when the user says "food-radar-tlv" or asks to monitor, search, or notify about new restaurants, cafes, bakeries, pop-ups, chef events, soft openings, reservation listings, hiring signals, or public social-media food-place signals in Tel Aviv or central Israel. Uses Tavily/web search and proof links, deduplicates against seen records, and outputs only new or meaningfully updated findings.
---

# Food Radar TLV

A narrow **monitoring / notification** skill. It detects **new food-place signals** around Tel Aviv
and central Israel and reports them with proof links. Each finding is something that is **new or
meaningfully changed** since the last run.

This is **NOT** a restaurant recommender, a "best restaurants" list, or a review writer. It only
surfaces *signals that a place or food event is new, opening, or about to open*.

## 1. Purpose

Detect, every run, signals of:
new restaurants · new coffee shops · bakeries · bars with food · chef restaurants · pop-up food
events · culinary collaborations · soft openings · "opening soon" places · new reservation listings ·
new event pages · hiring posts that imply a new place is opening · chef / restaurant-group hints
about new projects.

**Also detect "scene-change / lifecycle" signals (not new venues, but worth knowing — same bar: real
+ proof + in-window):**
- **Chef / key-personnel change** — head/exec chef, pastry chef, sommelier or bar manager **leaves or
  joins** an existing place (often precedes a new venue elsewhere). *e.g. Gal Ben Moshe leaving Pastel.*
- **Ownership / partner / investor change** — new owner/partner joins, or a group acquires a venue.
  *e.g. a star chef joining an existing restaurant as partner.*
- **Closure** — a notable place **closes** (frees a prime space; signals a scene shift; the space often
  reopens as something new — track it).
- **Relocation** — an existing venue **moves** to a new address.
- **Rebrand / concept change / relaunch** — same place, **new identity/concept/name**.
- **Expansion / new branch** — an existing brand opens a **second location**.
- **Brand entering the market** — an out-of-town / international brand opens its **first** local venue.
- **Major recognition** *(lower priority)* — Michelin / 50 Best / notable award or ranking change.

These are **"meaningful update"** signals (§9). Output them with the matching `status`/`signal_types`
(§6, §12) — and the same hard rules apply: real proof URL, in time-window, geography gate, and
**proof-link verification (§5)**. Treat a chef/ownership change or a closure of a known venue as a
**lead** for a *future* opening, too.

## 2. Trigger

The exact routine trigger is:

```
food-radar-tlv
```

Long form (if the routine allows extra instructions):

```
food-radar-tlv. Use Tavily as the primary search/extract/crawl/map tool. Search the last 24 hours
for new or meaningfully updated Tel Aviv / center-Israel food-place signals, including public indexed
social media. Return only findings with proof links. If nothing is found, return the exact
no-findings sentence.
```

## 3. Default time window

If the user gives no window:
- Search the **last 24 hours**.
- **Also** include strong "opening soon" signals from the **last 7 days**.
- Honor overrides: "last 7 days", "last 30 days", a specific date range, etc.

## 4. Source categories

Search all categories every run. Full lists live in **`sources.md`**. Summary:
1. **Israeli food / news media** — Time Out TLV/Israel, Mako (Eats), Ynet food, Walla food, Haaretz
   food (if accessible), Secret Tel Aviv, Debbest Food, local food blogs / newsletters / event calendars.
2. **Reservation / listing platforms** — Ontopo, Tabit, Google Maps / Google Business public results,
   Israeli local business listings (if accessible), restaurant sites, menu pages, event pages.
3. **Public *indexed* social signals** — Instagram, TikTok, Facebook public pages/events, LinkedIn
   public hiring posts, public creator / chef / restaurant pages (indexed search only — see §6).
4. **Hiring / opening signals** — HE + EN "now hiring for a new place" phrasing (see `search-queries.md`).

## 5. Tool resolution + Tavily-first workflow

**Resolve the search tool once, at the start of the run, in this order. Announce which one you used.**

1. **Tavily MCP tools** (`tavily_search`, `tavily_extract`, `tavily_crawl`, `tavily_map`) — preferred.
   Tool names may be prefixed (e.g. `mcp__...__tavily_search`); use whatever Tavily tools are present.
2. **Tavily Python SDK / REST** via `TAVILY_API_KEY` env var — run a small Python/`curl` call
   (`POST https://api.tavily.com/search`, `/extract`). Use when MCP tools are absent but the key is set.
3. **Built-in `WebSearch` / `WebFetch`** — last resort. ⚠️ `WebSearch` is **US-only**, so Hebrew /
   Israel coverage degrades badly. If you fall back to this, **say so in the report header** so the
   user knows results are partial, and lean on `site:`/domain queries + `WebFetch` on specific URLs.

If **no** Tavily path is available, tell the user how to enable it, then continue with the fallback:

```
# OAuth
claude mcp add tavily-remote-mcp --transport http https://mcp.tavily.com/mcp/
# API key
claude mcp add --transport http tavily https://mcp.tavily.com/mcp/?tavilyApiKey=<your-api-key>
# or set the env var for the SDK/REST path
export TAVILY_API_KEY=<your-key>
```

**Tavily usage by capability:**

- **Search** — broad web discovery + source-specific + indexed-social discovery. For recency, use
  `topic: "news"` with `days: 1` (or `time_range`/`start_date`/`end_date` for overrides). Use
  `include_domains` for source-specific and `site:`-style social queries. Run **Hebrew and English**.
- **Extract** — run on **every promising URL** to pull: title · text · publication date (if any) ·
  source name · place/event name · area/neighborhood · opening/event date (if any) · **proof
  sentence** · URL. To stay economical for a recurring routine, extract the **top ~15–25** candidate
  URLs per run, prioritizing official/reservation/media over weak social.
- **Crawl** — carefully, on known public pages where new items appear: Time Out TLV food pages, Mako
  food/restaurant-news, Ontopo TLV listings, Tabit listings/events, Secret Tel Aviv food/events,
  Debbest Food openings, public event calendars. (Specific URLs in `sources.md`.)
- **Map** — when a source has many pages and you need newly added URLs: reservation category pages,
  event pages, food-news archives, restaurant category pages.

**Mandatory reservation-platform check (every run — never skip):** You MUST query **both Ontopo and
Tabit** on every run, even if web/media search already looks "done." Do all of: (a) `tavily_map` the
Ontopo TLV category pages and the Tabit listings to enumerate venue/reservation URLs; (b) `tavily_search`
each platform (`include_domains`) for "new"/"חדש"/"בקרוב" venues **and** for the specific names you found
elsewhere this run (a fresh reservation page is itself a strong signal and a confidence booster). A new
or newly-bookable reservation page is a first-class finding — log it even when no media has covered it
yet. If a platform returns nothing usable, say so explicitly in the run notes (don't silently skip it).
Full URLs + method in **`sources.md` → "Mandatory every-run reservation checks"**.

**Anti-hallucination rule (hard):** every proof URL and date must come from an **actual tool result**.
Never guess, autocomplete, or invent URLs or dates. If you cannot obtain a real proof URL, **drop the
item** — do not output it.

**Anti-conflation rule (hard):** a search result's `content`/`raw_content` often **merges** the caption,
**OCR'd image text**, comments, and even adjacent listings into one blob. **Do not stitch fragments into
a claim.** Each asserted fact (it's *new*; it's a *bistro*; the *operator/chef*; the *date*) must trace
to the **same** source, and a venue/operator name must be confirmed from a **clean, untruncated** source
(the caption itself, the venue/reservation page, or a second post) — never from a truncated title
(`…`), an OCR layer alone, or your own inference. If a piece is OCR-only or comes from a different
listing, say so or drop it. (E.g.: a generic group cook-hiring caption + an OCR "new French bistro"
line ≠ "new bistro by that group.")

**Proof-link verification (hard — do this before output, for EVERY cited URL):** a search result's
`content` snippet is **not** proof that the cited URL is about your claim. Aggregator pages — TikTok
`/discover/` and `/video/`, IG explore, "related videos" — return snippets that **bundle many clips'
text** and bridge unrelated fragments with "…". So:
1. **Re-extract each proof URL** (or rely on its page **title**) and confirm the entity/claim actually
   appears **on that page**. The Tavily **title** is usually URL-specific and trustworthy; the
   **content snippet is not** when the title is generic/unrelated.
2. If the claim is present **only** in a content snippet and the page **title is unrelated**
   (e.g. a TikTok video titled about a lawsuit, captioned generically) → the link is **wrong → drop it**.
3. If the page is **gated** (login wall) and unconfirmable, treat the proof as **unverified**: keep the
   item only if it has another verified proof; otherwise → `watch`, noting "single/gated source".
4. An item with **no verified proof survives → do not report it** (move to `watch`).
Verified examples this is meant to catch: a "Moshik Roth new stand" / "Korean-café pop-up" whose TikTok
`/video/` titles were actually unrelated clips — the food text was merged in by the aggregator.

**Dating rule (incl. social):** Prefer an explicit date in the page/post body. **If the body has no
date, use the date the item was *posted/published*** — the platform/extract timestamp (e.g. Tavily's
publication date, an Instagram/TikTok/Facebook "posted on" / "Video by X on <date>" indicator, or an
event page's listed date). A tool-surfaced posted-date **counts as the signal date** for the time-window
test, so a post with no in-text date is **not** automatically dropped — only drop it if **no** real
posted-date can be obtained from a tool result. Always record where the date came from (body vs posted).

**Forward-date rule (pop-ups & events — MANDATORY for type `pop-up`/`event`):** For these two types the
eligibility gate is the **event date / run window — NOT the posted date**. Only output a pop-up/event if
its event date (or the run **end**-date for a multi-day run) is **today or later** (Asia/Jerusalem);
**drop anything that already ended.** Keep the posted date for recency, but record the **event date**
separately (`event_date` / `runs_until` — see `output-schema.md`). Get it by **extracting the event
page** (Secret Tel Aviv ticket pages, Ontopo event pages, Facebook events, or the post body) and reading
the explicit date / date-range — never infer "upcoming" from the posted date alone. Venues
(`opened` / `opening_soon` / `soft_opening`) are unaffected by this rule.

**Tavily mode for Israel/Hebrew (important):** the `news` topic is **US-biased** and returns irrelevant
results for Hebrew queries. Use `topic: "general"` + **`country: "israel"`** + `time_range` (or
`start_date`+`end_date`) for recency instead. Reserve `news`+`days` for English wire coverage only.

**Social posted-date decoding (reliable, free):** Instagram shortcodes and TikTok IDs encode the post
creation time — decode them to date a post with no in-text date. IG: base64-decode the shortcode
(alphabet `A–Za–z0–9-_`) → media id, then `((id >> 23) + 1314220021721)` ms = post time. TikTok:
`int(video_id) >> 32` = unix seconds. **Validate once per run** against a post whose date is visible,
then trust it; a decoded timestamp is a tool-derived posted-date, not a guess.

## 6. Social-media workflow

Social media is the **PRIMARY DISCOVERY ENGINE** of this skill — **lean on it heavily every run.**
It is the fastest, richest source for the most interesting finds (pop-ups, soft launches, chef
collabs, one-off/guest-chef nights, "hidden"/secret dinners) — usually days or weeks before media or
reservation platforms. It is still **not the final truth source**: discover on social, then **verify
before output** and attach a proof URL. Do not let a run lean only on media — social comes first.

**Improvise creative query combinations every run.** Don't just run the fixed lines — mix a TRIGGER
(pop-up / soft opening / guest chef / one-night / collab / "this week only") with an ANGLE (taco,
ramen, natural wine, matcha, rooftop…) and a NEIGHBORHOOD (Florentin, Jaffa, Montefiore, Levinsky…),
in **Hebrew and English**, and **invent fresh combinations** so each run surfaces new things and
doesn't re-fetch the same set. The seed lists + `combination_bank` live in **`social-watchlist.yaml`**;
the worked examples are in **`search-queries.md` group E**. Aim wide and weird — that's where the
interesting stuff hides.

Workflow:

1. Find social signal (via Tavily indexed search — see `search-queries.md` group E + the
   `combination_bank` in `social-watchlist.yaml`; run many creative combos, HE + EN).
2. Extract place/event/person name.
3. **Date it.** Read the date from the post body; if none, use the **posted/published date** surfaced
   by the tool (platform timestamp, "posted on"/"Video by X on <date>" indicator) — see §5 Dating rule.
   Apply the time-window test to that date. Do **not** drop a post just because it lacks an in-text date.
4. Search Tavily for that same entity across the web.
5. Confirm against food media / reservation platforms / Google Maps / event pages.
6. Score confidence (§10).
7. Output **only** if new or meaningfully updated, **and only with a proof URL**.

**Top chefs / restaurant groups / top restaurants (run every time):** Actively sweep the leading
Israeli chefs, restaurant groups, and top restaurants for **hiring posts** ("דרושים…", "צוות הקמה",
"opening team") and **new-project hints** — a top chef/group hiring an opening team almost always
precedes a new venue. Use the named seeds in **`social-watchlist.yaml`** (chefs · restaurant_groups ·
top_restaurants) and the hiring/chef query banks (`search-queries.md` groups C and F). Treat a
hiring/new-project signal from a known chef or group as a real lead: extract the implied venue, verify
(§ steps 4–5), and log it (often confidence 3 until corroborated).

Signal types: `official_announcement` · `chef_hint` · `creator_mention` · `hiring_signal` ·
`tagged_location` · `pop_up_announcement` · `supplier_or_designer_hint` · `reservation_link_shared` ·
`event_page_shared` · `chef_change` · `ownership_change` · `closure` · `relocation` · `rebrand` ·
`expansion` · `brand_entry` · `recognition`.

For every social finding store: platform · public URL · public handle/page name · caption excerpt ·
date (if any) · detected signal type · extracted place/event name · confidence · proof links.
Prefer **social signal + independent web/reservation proof**. Never output a social finding without a
proof URL. The starter account/hashtag/keyword watchlist is **`social-watchlist.yaml`**.

**Do not** log in, scrape private pages, bypass CAPTCHAs/paywalls/rate-limits/robots, impersonate
anyone, DM anyone, or collect private personal data. See **`compliance.md`**. Use official platform
APIs or Apify/other MCP connectors **only** if credentials/permissions exist and only for public data.

## 7. Search queries

Run **both Hebrew and English** every time. Full banks (A broad-HE, B broad-EN, C hiring, D
source-specific `site:`, E indexed-social) and the HE/EN keyword glossary are in
**`search-queries.md`**. Do not skip the Hebrew banks — they find most local signals.

## 8. Deduplication & normalization

The same place often appears in Hebrew and English and across sources — **merge into one record**.
Normalize before comparing:
- Tel Aviv / TLV / תל אביב ; Yafo / Jaffa / יפו
- cafe / café / coffee shop / בית קפה ; restaurant / מסעדה
- pop-up / popup / פופ אפ / פופאף
- soft launch / soft opening / הרצה / סופט לאנץ׳

Optional helper: `python3 scripts/normalize_findings.py` (normalizes HE/EN names, cities, status, and
fuzzy-dedupes; also merges items that share a proof URL). The skill works without it. **You** must do
the **Hebrew↔English transliteration merge** (e.g. "Bua Bakery" = "מאפיית בועה") — the script can't
transliterate; decide via a shared proof URL, address, or chef/owner name.

## 9. Seen-records logic

State file: **`seen-records.json`** (same folder). `seen-records.example.json` shows the shape.

- **If it exists:** load it **before** searching. Do **not** re-output old findings unless there is a
  **meaningful update**.
- **If it does not exist:** create it after the first run.

A **meaningful update** = any of: official opening date found · new reservation page · new event date ·
new media coverage · new official social post · new hiring signal that changes confidence · location/
address confirmed · status changed (e.g. rumor/opening-soon → opened).

Per record store: `normalized_name` · `original_names` · `type` · `area` · `status` · `first_seen_at`
· `last_seen_at` · `proof_urls` · `source_names` · `confidence` · `signal_types` · `notes` ·
`last_output_at`. Optional helper: `python3 scripts/update_seen_records.py` merges new findings into
the file. Schema details in **`output-schema.md`**.

## 10. Confidence scoring (1–5)

- **5** = official venue/chef/restaurant-group announcement, OR reservation page **plus** another
  independent source.
- **4** = credible media source, OR official social post.
- **3** = multiple weak signals (e.g. hiring post + tagged location + chef hint).
- **2** = one weak signal only.
- **1** = rumor or unclear mention.

## 11. Geography gate

- **Tel Aviv-Yafo** = primary; always eligible.
- **Secondary (Gush Dan / central Israel)** — Ramat Gan, Givatayim, Herzliya, Ramat HaSharon, Holon,
  Bat Yam, Bnei Brak, Petah Tikva, Rishon LeZion, Ra'anana, Kfar Saba, Hod HaSharon — include **only
  on a strong signal**: confidence **≥ 3**, or one official/reservation-page source.

## 12. Required output format

```
# Food Radar TLV — New Findings

Window searched: `<time window>`
Run date: `<date/time>`

## New / Updated Places

1. `<place or event name>`

   * Type: restaurant / cafe / bakery / bar / pop-up / event / unknown
   * Area: Tel Aviv neighborhood or city
   * Status: opened / opening soon / soft opening / pop-up / event / hiring signal / rumor /
     chef change / ownership change / closing / relocating / rebrand / expansion / recognition
   * Event date: `<date or date-range>`   ← REQUIRED for pop-up/event; must be today-or-later (see §5 forward-date rule); omit for venues
   * Why found: one short reason
   * Proof:

     * `<source name>` — `<URL>` — `<date if available>`
     * `<source name>` — `<URL>` — `<date if available>`
   * Confidence: 1–5
   * Notes: one short sentence only
```

Rules: **no place/event without ≥1 proof URL**. Prefer findings backed by official source / reservation
page / credible media / public social post / public hiring post / event page. Keep it a **list with
proof links — no essay.**

## 13. No-findings output

If nothing new is found, output **exactly** this and nothing else:

```
No new food-place signals found for Tel Aviv / center Israel in this run.
```

## 14. Compliance

Public information or authenticated APIs you have permission to use, only. Do not bypass logins,
paywalls, CAPTCHAs, rate limits, or robots restrictions. Do not impersonate, DM, make reservations,
apply to jobs, contact venues, or collect private personal data. For social posts store only public
URL, public handle/page name, caption excerpt, date, and why it's relevant. No proof → no output.
Full rules in **`compliance.md`**.

## 15. Run algorithm (deterministic)

1. Resolve search tool (§5) and announce it.
2. Load `seen-records.json` if present.
3. Run query banks A–G (`search-queries.md`) in **Hebrew and English**, scoped to the time window
   (G = scene-change / lifecycle: chef/ownership change, closure, relocation, rebrand, expansion).
4. Collect candidate URLs; **Extract** the top ~15–25 (official/reservation/media first).
5. **Crawl/Map** the known high-value pages from `sources.md` for newly added items.
6. **Reservation platforms — MANDATORY, both, every run:** map + search **Ontopo** and **Tabit**
   (§5 "Mandatory reservation-platform check"). Capture new/newly-bookable venue pages, and pull
   reservation links for the run's other candidates. Note explicitly if a platform yields nothing.
7. **Chefs/groups/top restaurants:** sweep `social-watchlist.yaml` seeds + query banks C & F for
   **hiring/opening-team posts** and new-project hints from leading chefs, groups, and top restaurants.
8. For each candidate: extract entity name, area/city, status, date (body date, or **posted date** per
   §5 Dating rule), proof sentence + URL.
9. Normalize (§8) and **dedupe** (merge HE/EN + cross-source duplicates).
10. Score confidence (§10); apply the **geography gate** (§11). For type `pop-up`/`event`, apply the
    **forward-date rule** (§5): extract the event date/run-window and **drop anything already ended**.
11. Diff against `seen-records.json`: keep brand-new items + meaningfully-updated items; drop the rest.
11b. **Proof-link verification (§5):** re-extract every cited URL and confirm the claim is on that page
    (title/body), not just a snippet. Drop wrong/merged-snippet links; an item with no verified proof
    left → `watch`, not reported.
12. Print the report (§12) — or the exact no-findings sentence (§13).
13. Write/update `seen-records.json` (set `last_output_at` on items you reported; you may also log
    undated discoveries and out-of-window items as tracked-but-unreported `watch`/`excluded` records).

## 16. Example output

```
# Food Radar TLV — New Findings

Window searched: `last 24 hours (+ 7d opening-soon)`
Run date: `2026-06-27 09:00 Asia/Jerusalem`

## New / Updated Places

1. Bua Bakery (sample)

   * Type: bakery
   * Area: Florentin, Tel Aviv
   * Status: opening soon
   * Why found: New reservation page + chef announcement post within 24h
   * Proof:

     * Ontopo — https://ontopo.com/he/il/example-bua — 2026-06-26
     * Instagram (@chef_example) — https://instagram.com/p/EXAMPLE — 2026-06-27
   * Confidence: 4
   * Notes: Soft launch reportedly next week; address listed on reservation page.
```
