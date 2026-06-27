# food-radar-tlv

A recurring **monitoring / notification** skill for **new food-place signals** around **Tel Aviv-Yafo**
and central Israel (Gush Dan). It sweeps web + indexed public social + food media + reservation
platforms + event pages + hiring posts, and reports findings **with proof links**, deduplicated
against local state.

It is **only** a radar. It is **not**:
- a restaurant recommender,
- a "best restaurants" list,
- a review writer.

## What it detects

New restaurants · coffee shops · bakeries · bars with food · chef restaurants · pop-up food events ·
culinary collaborations · soft openings · "opening soon" places · new reservation listings · new event
pages · hiring posts that imply a new place is opening · chef / restaurant-group hints about new projects.

## Trigger

Run the routine with exactly:

```
food-radar-tlv
```

Long form (if your routine allows extra instructions):

```
food-radar-tlv. Use Tavily as the primary search/extract/crawl/map tool. Search the last 24 hours
for new or meaningfully updated Tel Aviv / center-Israel food-place signals, including public indexed
social media. Return only findings with proof links. If nothing is found, return the exact
no-findings sentence.
```

You can override the window: e.g. `food-radar-tlv last 7 days`.

## Setup — Tavily (recommended)

The skill prefers **Tavily** for search/extract/crawl/map because the built-in `WebSearch` is **US-only**
and weak for Hebrew/Israel queries. Enable one of:

```bash
# OAuth (remote MCP)
claude mcp add tavily-remote-mcp --transport http https://mcp.tavily.com/mcp/

# API key (remote MCP)
claude mcp add --transport http tavily https://mcp.tavily.com/mcp/?tavilyApiKey=<your-api-key>

# or, for the Python SDK / REST fallback path:
export TAVILY_API_KEY=<your-key>
```

Check it's live: `claude mcp list` should show a Tavily entry as **Connected**.

**Fallback chain** (the skill resolves this automatically and tells you which it used):
Tavily MCP tools → Tavily SDK/REST via `TAVILY_API_KEY` → built-in `WebSearch`/`WebFetch` (US-only;
report header will warn you that coverage is partial).

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Main skill: workflow, scoring, output contract, run algorithm |
| `sources.md` | Full source lists + pages to crawl/map |
| `search-queries.md` | Hebrew + English query banks (A–E) + keyword glossary |
| `social-watchlist.yaml` | Starter accounts / hashtags / keywords to watch |
| `output-schema.md` | Finding + seen-record JSON schema |
| `seen-records.example.json` | Example of the local state file |
| `compliance.md` | Public-data-only / no-bypass rules |
| `scripts/normalize_findings.py` | Optional: normalize + fuzzy-dedupe findings (Python 3.9+, stdlib) |
| `scripts/update_seen_records.py` | Optional: merge new findings into `seen-records.json` (Python 3.9+, stdlib) |

`seen-records.json` (the live state file) is created on first run. Consider adding it to `.gitignore`
so run state isn't committed.

## How a run works

1. Resolve the search tool (Tavily preferred) and announce it.
2. Load `seen-records.json` (if present).
3. Run query banks A–E in **Hebrew and English** for the time window.
4. Extract the top candidate URLs (proof title/text/date/sentence).
5. Crawl/Map the known high-value pages for newly added items.
6. Normalize + dedupe + score confidence + apply the geography gate.
7. Diff against seen-records → keep brand-new + meaningfully-updated items.
8. Print the report (or the exact no-findings sentence) and update `seen-records.json`.

## Sample output (fake data — for format verification only)

```
# Food Radar TLV — New Findings

Window searched: `last 24 hours (+ 7d opening-soon)`
Run date: `2026-06-27 09:00 Asia/Jerusalem`

## New / Updated Places

1. Lila Wine Bar (sample)

   * Type: bar
   * Area: Lev Ha'ir, Tel Aviv
   * Status: soft opening
   * Why found: Time Out item + new Ontopo reservation page within 24h
   * Proof:

     * Time Out Tel Aviv — https://www.timeout.co.il/example-lila — 2026-06-27
     * Ontopo — https://ontopo.com/he/il/example-lila — 2026-06-26
   * Confidence: 5
   * Notes: Chef-led natural-wine bar; soft launch this weekend per the article.

2. דרושים — מאפייה חדשה (sample hiring signal)

   * Type: bakery
   * Area: Ramat Gan
   * Status: hiring signal
   * Why found: LinkedIn "opening team" post for an unnamed new bakery
   * Proof:

     * LinkedIn — https://www.linkedin.com/posts/EXAMPLE — 2026-06-25
   * Confidence: 3
   * Notes: Secondary city; included because hiring post names a Q3 opening.
```

If nothing new is found, the run prints exactly:

```
No new food-place signals found for Tel Aviv / center Israel in this run.
```

## Compliance (short)

Public data or authenticated APIs you're permitted to use, only. No bypassing logins / paywalls /
CAPTCHAs / rate limits / robots. No impersonation, DMs, reservations, job applications, or contacting
venues. No private personal data. No proof URL → no output. Full rules in `compliance.md`.
