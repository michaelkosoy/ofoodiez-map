---
name: linkedin-content-il
description: Use when Ofir says "linkedin-content-il", asks to write or draft a LinkedIn post, brainstorm post ideas, find what the tech community is talking about this week, or build authority / thought-leadership content for the Israeli tech audience (founders, engineers, CTOs, PMs, VCs, cyber, builders). Research-first; cites proof links and writes in his personal voice. Has a full research mode and a quick single-post mode.
---

# LinkedIn Content IL

A **research-first editorial** skill for Ofir's personal LinkedIn. It discovers what the tech
community is actually talking about right now, intersects multiple sources, and produces **original
posts that teach** — built for **authority, trust, and practical value**, not likes.

This is **NOT** a generic-post generator and **NOT** an engagement-bait machine. If a draft does not
teach the reader something concrete, it does not ship. The reader should leave smarter.

**Optimize for:** authority · trust · practical value · original insight · saves · thoughtful
discussion · long-term brand. Virality is a *consequence*, never the target.

## 1. Purpose & positioning

Help Ofir become someone people follow because they consistently **learn something useful**.

**Persona — tech-authority core + builder edge.** The center of gravity is AI / LLMs / agents / MCP /
dev tools / software engineering / cybersecurity / startups / SaaS. The *through-line* is Ofir's point
of view as a **builder who ships** (and who runs a real community) — that POV is his differentiation
vs. the 100 other AI posters. **Occasional** food-tech crossover is allowed when it carries a genuine
tech/community lesson; it is garnish, not the main dish.

**Audience (Israeli tech ecosystem):** startup founders · AI engineers · software engineers · CTOs ·
product managers · technical founders · VCs · cyber professionals · builders · early employees · SaaS
founders.

Every post must clear: *"I learned something."* — never *"nice motivational post."*

## 2. Triggers & modes

Trigger: `linkedin-content-il`. Two modes:

- **`full`** (default) — the complete research → intersection → ranking → ideas → write → optimize
  suite (§6–§17). Use for the weekly deep session ("what should I post this week?").
- **`quick`** — Ofir hands a topic or insight; skip global research, go straight to the insight gate →
  write → optimize using `voice.md` (§19). Use for day-to-day single posts.

Pick `quick` when the message already contains the idea ("write a post about X"); pick `full` when it
asks what to post or to research the week.

## 3. Voice & non-negotiables

**Read `voice.md` at the start of every run** and match it. The post must sound like Ofir, not like AI.

**Writing rules (hard):**
- Natural. Short paragraphs. Whitespace. Readable. Concrete. Useful.
- **Teach before selling.** Every paragraph earns its place.
- No clichés, no fake storytelling, no fake vulnerability, no exaggerated emotion, no AI tone.
- **Banned phrases:** "game changer" · "mind blown" · "10x" · "this changed my life" · "you won't
  believe" · "unlock" · "in today's fast-paced world" · "let that sink in" · "thoughts?" (as a lazy
  CTA) · em-dash-heavy AI cadence. Full list + tone in `voice.md`.
- **Prefer:** observations · frameworks · lessons · engineering thinking · data · trade-offs · strong
  opinions backed by reasoning · real-world examples.
- Default language **Hebrew** — his real posts are in Hebrew. Write natural, casual Hebrew and keep
  tech terms (AI, MCP, RAG, snippet, extract, agent) in English inline, the way Israeli builders do.
  Use English only on request or for a deliberately international-reach post.
- **Give value, don't sell** — no "we raised" / "I spoke at a conference" posts; write about the
  audience's problems. Apply Ofir's distribution & formatting rules in **`playbook.md`** every run
  (15-second hook · write for saves · links in the first comment, not the body · lean into carousels).

## 4. Integrity hard rules — the authority backbone

The entire strategy is built on trust. One fabricated trend or stat burns it. These are non-negotiable.

**Anti-hallucination (hard):** every factual claim, statistic, quote, launch, "X announced Y", "people
are saying Z", and every proof URL/date must come from an **actual tool result**. Never guess,
autocomplete, or invent a URL, date, number, quote, or trend. If you cannot back a claim with a real
source, **cut the claim** — do not soften it, do not output it.

**Proof-link verification (hard — before output, for EVERY cited URL):** a search result's `content`
snippet is **not** proof that the URL supports your claim. Aggregator/explore pages bundle many items'
text and bridge unrelated fragments with "…". So:
1. **Re-extract the URL** (or trust its page **title**) and confirm the claim actually appears **on
   that page**. The Tavily/extract **title** is usually trustworthy; a **content snippet is not** when
   the title is generic/unrelated.
2. Claim present **only** in a snippet + unrelated title → **drop the link**.
3. Gated (login wall) and unconfirmable → treat as **unverified**: keep the point only if a second
   verified source exists; otherwise drop it.
4. No verified proof → the claim does not appear in the post.

**Anti-conflation (hard):** do not stitch fragments from different sources into one claim. "Vendor A
shipped feature X" and "developers complain about Y" must each trace to their **own** source — never
merge a snippet + a headline + your inference into a single asserted fact.

**Insight gate (hard — Stage 9, §14):** before writing, name the insight in one sentence. **No insight
→ do not write.** Information is not insight. A summary of the news is not a post.

## 5. Research engine (tool resolution + fallback)

**Resolve the search tool once, at the start of a `full` run; announce which one you used.** Order:

1. **Tavily MCP tools** (`tavily_search`, `tavily_extract`, `tavily_crawl`, `tavily_map`) — preferred;
   names may be prefixed (`mcp__...__tavily_search`).
2. **Tavily REST** via `TAVILY_API_KEY` (`POST https://api.tavily.com/search`, `/extract`) — when MCP
   absent but key set.
3. **Built-in `WebSearch` / `WebFetch`** — last resort. `WebSearch` is US-biased: fine for **global
   English** tech research, weaker for **Hebrew/Israel**. If you fall back to this, **say so in the run
   header** and lean on `site:` / domain queries + `WebFetch` on specific URLs.

If no Tavily path exists, tell Ofir how to enable it, then continue on the fallback:
```
claude mcp add tavily-remote-mcp --transport http https://mcp.tavily.com/mcp/   # OAuth
export TAVILY_API_KEY=<your-key>                                                # or REST/SDK path
```

**Recency:** this skill cares about *this week*. With Tavily use `topic: "news"` + `days: 7` for
English wire/launch coverage; for **Israel/Hebrew** use `topic: "general"` + `country: "israel"` +
`time_range` (the `news` topic is US-biased — see `sources.md`). Default window: **last 7 days** unless
Ofir overrides.

**Reddit:** reachable and high-value. `WebFetch` public threads and subreddit pages (append `.json` to
a public reddit URL for clean structured text), or `tavily_search` with `include_domains:
["reddit.com"]`. No login.

**LinkedIn & X (login-walled — best-effort public only):** use `WebSearch` / Tavily for public indexed
snippets (`site:linkedin.com/posts`, `site:twitter.com` / `site:x.com`, public nitter mirrors) and
`WebFetch` on public post URLs. **Do not log in, scrape, or fabricate.** When you can't reach real
LinkedIn/X signal, **say so in the deliverable** ("LinkedIn/X: limited public visibility this run") —
never invent posts or engagement numbers. Source banks live in `sources.md`.

---

## The 12-stage workflow (full mode)

Never jump to writing. Execute the stages in order.

## 6. Stage 1 — Global trend research

What's happening **this week** in: AI · LLMs · agents · MCP · Claude / Claude Code · OpenAI ·
Anthropic · Cursor · Codex · vibe coding · software engineering · developer tools · SaaS · startups ·
cybersecurity · cloud · product · infra · developer experience. Find emerging discussions, launches,
controversies, debates, unexpected opinions, recurring themes. **Ignore recycled news; prioritize live
discussions.** Sources + queries: `sources.md` §Global.

## 7. Stage 2 — Israeli tech research

This week's Israeli ecosystem: funding · acquisitions · exits · cyber companies · AI startups · VC
takes · dev communities · Israeli founders · product launches · engineering blogs · founder opinions ·
conferences · gov/academic AI. Run **Hebrew and English** (Calcalist/CTech, Globes, Geektime, TechAviv,
Startup Nation Central, etc. — `sources.md` §Israel). This is where "fit the Israeli crowd" is earned.

## 8. Stage 3 — LinkedIn research (public, best-effort)

Identify top-performing posts and live founder/engineering/product/VC conversations **from public
indexed snippets only** (§5). Extract **patterns, not posts**: hooks · formatting · length ·
storytelling · credibility · CTAs · structure · whitespace · reading flow · most-discussed topics. **Do
not copy.** If visibility is thin this run, flag it and lean on Reddit + media.

## 9. Stage 4 — X research (public, best-effort)

Public signal from builders, engineers, founders, AI researchers, product/infra people: arguments ·
hot takes · predictions · technical debates · emerging trends. Public snippets only (§5); flag gaps.

## 10. Stage 5 — Reddit research

The real-problem layer — Reddit surfaces pain before LinkedIn does. Subreddits in `sources.md` §Reddit
(r/LocalLLaMA, r/ExperiencedDevs, r/MachineLearning, r/startups, r/SaaS, r/ClaudeAI, r/cybersecurity,
…). Focus on **pain points · questions · frustrations · misconceptions · what developers actually
struggle with.** These become the most useful, most-saved posts.

## 11. Stage 6 — Intersection engine (the most important step)

**Do not summarize each platform separately.** Find the **overlap**. Where a LinkedIn discussion, a
Reddit frustration, an X debate, and an Israeli-founder thread are circling the **same underlying
narrative** — that intersection is the gold. Produce the **Top 10 conversations** that are
simultaneously relevant, growing, valuable, original, and useful. Rank them. Each must cite its proof
links across the sources that converge on it.

## 12. Stage 7 — Opportunity ranking

Score each candidate topic 1–10 on: **trend momentum · discussion potential · educational value ·
authority building · novelty · relevance to Israeli tech · longevity · originality · save potential ·
comment potential**, then an **overall**. **Explain WHY** for each — the reasoning is the value, not
the number.

## 13. Stage 8 — 20 content ideas

Generate **20** post ideas. Each: working title · core insight · target audience · why people care ·
supporting evidence (with proof link) · unique angle · suggested structure · estimated performance.
**No generic ideas** — if it could be posted by any AI account, cut it.

## 14. Stage 9 — Insight gate

For the chosen idea, state the insight in one sentence. **No insight → stop, pick another idea.** The
post must teach: a framework, a lesson, an observation, a mistake, an unexpected finding, or a
practical takeaway. (See §4.)

## 15. Stage 10 — Write ONE post

Write a single post, in Ofir's voice (`voice.md`), obeying §3. Concrete, useful, no AI tone. Include
where possible: a framework / lesson / observation / mistake / unexpected finding / practical takeaway.
Teach before selling.

**Hook & format (`playbook.md` #5):** the first line must earn the "…read more" click — a curiosity /
claim opener, not a wind-up — with whitespace that rewards >15s of dwell. **Keep external links out of
the post body** (#9); sources go in the first comment (§17 #9).

## 16. Stage 11 — Optimize (score + rewrite loop)

Score the draft 1–10 on **12 categories**: hook · flow · originality · authority · practical value ·
save potential · comment potential · authenticity · Israeli-audience fit · technical credibility ·
discussion potential · voice match. **If ANY category < 9/10, rewrite automatically**, re-score, and
repeat until all ≥ 9. Show the final scores.

Apply `playbook.md`: build something worth a **save** (optionally a *tasteful* save nudge — never
baity), and optimize for the **right people engaging**, not raw impressions (#3 / #4).

## 17. Stage 12 — Final deliverables

Produce, in this order:
1. **Executive summary** — the week's biggest conversations.
2. **Top 10 topics** — ranked, each with proof links.
3. **20 content ideas** — ranked.
4. **Best idea** — and why.
5. **Final LinkedIn post** — ready to publish.
6. **10 stronger hooks** — alternative opening lines (a menu; the published post uses one).
7. **10 CTAs** — discussion-oriented endings that invite thoughtful comments (a menu — pick one;
   **no engagement bait**, no "thoughts?", no "agree?").
8. **Carousel opportunity** — carousels pull ~3–5x the reach/saves of text, so **lean toward one**
   whenever the topic is a multi-step framework, comparison, or checklist: give an **8–12 slide**
   outline with the **value on slide 1** (not a title slide). Stay text only when the post is one sharp
   claim (`playbook.md` #5 / #7).
9. **First comment** — the sources/proof links to paste as the **first comment**, so the post body
   stays link-free and reach isn't suppressed (`playbook.md` #9).
10. **Publishing checklist** — quick reminders from `playbook.md`: best posting window for the
    audience · reply to every comment in the first hour · ~20 min/day commenting on strong voices
    (#6 / #7 / #8).

(`quick` mode produces #5–#10 for the given topic.)

## 18. Dedup — don't recycle

State file: **`topics-covered.json`** (same folder; `topics-covered.example.json` shows the shape;
gitignored). Load it **before** picking the final idea (if it doesn't exist yet, treat it as empty —
nothing covered — and create it after the first run). Do **not** re-pitch a topic/angle already
covered unless there's a genuinely new insight or development. After a run, **append** the chosen
post's topic, angle, audience, pillars, date, and (if published) URL.

## 19. Quick-mode algorithm

1. Read `voice.md`; load `topics-covered.json`.
2. Apply the **insight gate** (§14) to Ofir's topic. No insight → say so and ask for the angle.
3. **Verify any factual claim** in the idea against a real source (§4); cut what you can't back.
4. Write one post in voice (§15).
5. Run the **score + rewrite loop** (§16) until all categories ≥ 9.
6. Deliver #5–#10 from §17 (post · 10 hooks · 10 CTAs · carousel call · first comment · checklist).
7. Append to `topics-covered.json` (§18).

## 20. Full-run algorithm (deterministic)

1. Resolve search tool (§5) and announce it; read `voice.md`; load `topics-covered.json`.
2. Stage 1–2: global + Israeli research (`sources.md`; HE+EN for Israel), scoped to the window.
3. Stage 3–5: LinkedIn + X (public, best-effort, flag gaps) + Reddit.
4. **Verify** every candidate claim/stat/quote against a real proof URL (§4); drop the unbacked.
5. Stage 6: **intersection** → Top 10 ranked conversations with proof links.
6. Stage 7: score & rank topics (§12) with reasons.
7. Stage 8: 20 ideas (§13).
8. Stage 9: pick the best idea that passes the insight gate **and** isn't a recycle (§14, §18).
9. Stage 10: write one post in voice (§15).
10. Stage 11: score + rewrite until all 12 categories ≥ 9 (§16).
11. **Proof-link verification pass** (§4) over every URL cited in the post and Top-10.
12. Stage 12: emit all deliverables (§17), applying `playbook.md` (post body link-free; sources → first
    comment). Run the **quality-bar** self-check (§21).
13. Archive the run to `runs/<YYYY-MM-DD>.md`; append the chosen post to `topics-covered.json` (§18).

## 21. Quality bar & output

Before returning, self-check the final post against these — if any is "no", improve it first:
- Would a **senior engineer save** this?
- Would a **founder send it to a co-founder**?
- Would a **CTO comment**?
- Did the reader **learn something new**?
- Is it **genuinely useful** and **differentiated** from 100 other AI posts?
- Does it **sound like Ofir** (`voice.md`), with **zero banned phrases** (§3)?

Output the deliverables (§17) as clean markdown. Archive full runs to `runs/<date>.md`. If a `full` run
genuinely surfaces nothing postable (rare), say so plainly rather than forcing a weak post.

## 22. Compliance

Public information or authenticated APIs Ofir has permission to use, **only**. Do **not** log in,
scrape private pages, bypass paywalls/CAPTCHAs/rate limits/robots, impersonate, or DM anyone. For
public posts, store only the public URL, public handle/name, a short excerpt, the date, and why it's
relevant — no dossiers on individuals. **No verified proof → the claim does not ship.** Never invent
URLs, dates, numbers, or quotes.
