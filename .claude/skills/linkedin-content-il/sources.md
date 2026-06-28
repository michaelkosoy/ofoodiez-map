# Sources & query banks — linkedin-content-il

Default window: **last 7 days**. Run global research in English; run **Israel research in Hebrew AND
English**. Every cited item needs a real proof URL (SKILL.md §4). URLs below are entry points, not
guaranteed deep links — always confirm via an actual tool result.

---

## Global (Stage 1) — what tech is talking about this week

| Source | Use | Entry point |
|--------|-----|-------------|
| Hacker News + Algolia search | Live discussion, what devs argue about | https://hn.algolia.com/ , https://news.ycombinator.com/ |
| Simon Willison's blog | AI/LLM practical analysis | https://simonwillison.net/ |
| Latent Space / The Pragmatic Engineer / InfoQ | Engineering + AI depth | discover via search |
| Vendor blogs/changelogs | Real launches (not rumors) | anthropic.com/news, openai.com/blog, cursor.com, github.blog, Google AI |
| Product Hunt / GitHub Trending | New tools, momentum | producthunt.com, github.com/trending |
| TechCrunch / The Verge / Ars Technica | Wire coverage, controversies | discover via search |

Tavily: `topic: "news"` + `days: 7` for English wire/launch coverage.

**Query starters:** `AI agents this week` · `MCP <topic> discussion` · `Claude Code vs Cursor` ·
`LLM eval <X>` · `developer experience complaint <tool>` · `<vendor> launch <feature> reaction` ·
`vibe coding limits` · `SaaS pricing AI` · `cybersecurity AI <threat/tool>`.

## Israel (Stage 2) — fit the Israeli crowd

| Source | Use | Entry point |
|--------|-----|-------------|
| Calcalist / CTech | Funding, exits, startup news (HE/EN) | calcalist.co.il , calcalistech.com |
| Globes | Business + tech | globes.co.il (EN: en.globes.co.il) |
| Geektime | Israeli startup/tech community | geektime.co.il |
| TheMarker — tech | Tech/business analysis | themarker.com |
| Startup Nation Central / Finder | Ecosystem data, company news | startupnationcentral.org |
| TechAviv / founder communities | Founder discussion | techaviv.com , discover via search |
| Israeli VC blogs (e.g. Aleph, Vintage, OurCrowd) | VC takes | discover via search |

Tavily for Hebrew: `topic: "general"` + **`country: "israel"`** + `time_range` (the `news` topic is
US-biased). Run both languages.

**Query starters (HE):** `גיוס סטארטאפ ישראלי` · `אקזיט חברה ישראלית` · `סטארטאפ AI ישראל` ·
`חברת סייבר ישראלית גיוס` · `מייסד ישראלי <נושא>` · `קהילת מפתחים ישראל`.
**Query starters (EN):** `Israeli startup funding this week` · `Israeli cyber company` ·
`Israel AI startup launch` · `Israeli founder <topic>` · `Tel Aviv tech community`.

## Reddit (Stage 5) — the real-problem layer

Reachable via `WebFetch` (append `.json` to a public reddit URL for clean text) or Tavily
`include_domains: ["reddit.com"]`. No login. Focus on **pain points, frustrations, misconceptions**.

Subreddits: r/LocalLLaMA · r/MachineLearning · r/ExperiencedDevs · r/programming · r/startups ·
r/SaaS · r/ClaudeAI · r/OpenAI · r/ChatGPTCoding · r/cybersecurity · r/devops · r/ArtificialIntelligence
· r/cscareerquestions.

**Query starters:** `site:reddit.com <tool> frustrating` · `<topic> "anyone else"` ·
`why does <X> keep <failing>` · `<framework> in production problems`.

## LinkedIn & X (Stages 3–4) — public, best-effort only

Login-walled. Use public indexed snippets only; **flag gaps, never fabricate** (SKILL.md §5/§22).

- LinkedIn: `site:linkedin.com/posts <topic>` · `site:linkedin.com/pulse <topic>` (extract **patterns**:
  hooks, structure, length, CTAs — never copy text).
- X: `site:twitter.com <topic>` · `site:x.com <handle>` · public nitter mirrors via `WebFetch`.

When visibility is thin, write in the deliverable: "LinkedIn/X: limited public visibility this run" and
lean on Reddit + media + Israeli sources.

---

## Recency & language reminders

- Window is **this week** unless overridden. Prefer items with a real, tool-surfaced date.
- Israel = Hebrew + English, every run. Hebrew finds most local signal.
- If you fall back to built-in `WebSearch` (no Tavily), **say so in the run header** — Hebrew/Israel
  coverage will be partial.
