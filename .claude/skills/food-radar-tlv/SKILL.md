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

**Anti-hallucination rule (hard):** every proof URL and date must come from an **actual tool result**.
Never guess, autocomplete, or invent URLs or dates. If you cannot obtain a real proof URL, **drop the
item** — do not output it.

## 6. Social-media workflow

Social media is an **early-signal layer, not the final truth source**. Workflow:

1. Find social signal (via Tavily indexed search — see `search-queries.md` group E).
2. Extract place/event/person name.
3. Search Tavily for that same entity across the web.
4. Confirm against food media / reservation platforms / Google Maps / event pages.
5. Score confidence (§10).
6. Output **only** if new or meaningfully updated, **and only with a proof URL**.

Signal types: `official_announcement` · `chef_hint` · `creator_mention` · `hiring_signal` ·
`tagged_location` · `pop_up_announcement` · `supplier_or_designer_hint` · `reservation_link_shared` ·
`event_page_shared`.

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
   * Status: opened / opening soon / soft opening / pop-up / event / hiring signal / rumor
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
3. Run query banks A–E (`search-queries.md`) in **Hebrew and English**, scoped to the time window.
4. Collect candidate URLs; **Extract** the top ~15–25 (official/reservation/media first).
5. **Crawl/Map** the known high-value pages from `sources.md` for newly added items.
6. For each candidate: extract entity name, area/city, status, date, proof sentence + URL.
7. Normalize (§8) and **dedupe** (merge HE/EN + cross-source duplicates).
8. Score confidence (§10); apply the **geography gate** (§11).
9. Diff against `seen-records.json`: keep brand-new items + meaningfully-updated items; drop the rest.
10. Print the report (§12) — or the exact no-findings sentence (§13).
11. Write/update `seen-records.json` (set `last_output_at` on items you reported).

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
