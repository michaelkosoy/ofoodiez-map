# Results & audience data ledger

Source of truth for every number shown on /portfolio, /portfolio/work and
/portfolio/results. Update this file AND the site content
(/admin/portfolio/content) together. Never publish a number that isn't
backed by a row here.

## Campaigns

| Field | Appcharge | Cato Networks | Cyera | Primis |
|---|---|---|---|---|
| Campaign | Startups Series reel (ep. 2) | Office-tour reel | Story, careers link | Story, link + creator tag |
| Goal | Employer awareness + candidate attraction | Employer awareness | Promote open roles | Awareness |
| Content type | Reel | Reel | Story | Story |
| Publication date | ❓ fill in | ❓ fill in | ❓ fill in | ❓ fill in |
| Platform | Instagram (my channels) | Instagram (my channels) | Instagram story | Instagram story |
| Views | ❓ (screenshot shows Engagement tab only) | 196,055 | 4,025 | ❓ (navigation 2,813) |
| Accounts reached | ❓ | 136,159 | 2,444 | ❓ |
| Likes / comments | 647 / 48 | 2.5K / 129 | 1 / 4 (clicks story) | 2 / 7 |
| Shares | 944 | 5.8K | 44 | 50 |
| Saves | 333 | 743 | — | — |
| Link clicks | 30 bio-link taps | — | **304 (careers link)** | 109 |
| Sticker taps | — | — | — | 164 (@ mention) |
| Profile visits | 1,920 | — | 15 (profile activity) | — |
| Follows | 413 | 894 | — | — |
| CV submissions | **251 → 578 (+327, ~130%, 2.3×)** week following publication | — | — | — |
| Reporting timeframe | Week following publication (CVs); insights cumulative | Cumulative @ 2026-07 | Cumulative @ 2026-07 | Cumulative @ 2026-07 |
| Data source | Instagram Insights + company ATS | Instagram Insights | Instagram Insights | Instagram Insights |
| Screenshot | `appcharge reel data.jpeg` | `cato netwroks reel data views.jpeg` | `cyera story views.jpeg`, `cyera story clicks carrers link.jpeg` | `primis story clicks.jpeg` |
| Permission to publish | ❓ confirm with company | ❓ confirm | ❓ confirm | ❓ confirm |

Screenshots collected 2026-07-29 (from ~/Downloads — keep copies somewhere
durable; NOT committed to the repo per the no-large-images rule).

Added 2026-07-30 (numbers provided by Ofir, Instagram Insights):
- **BeyondTrust** — 1 story with link: 3,653 views · 98 link clicks (❓ screenshot + permission)
- Reel refresh: Cato 204K views / 2,508 likes / 5,847 shares · Mate Security 107K / 902 / 910 · Appcharge 103K / 662 / 945
- Totals shown on site now: 400K+ content views · 500+ story link clicks (304+109+98)

## Audience (Instagram Insights, collected 2026-07)

- Age: 13-17: 0.2% · 18-24: 4.7% · **25-34: 31.9%** · 35-44: 21.7% · 45-54: 20.6% · 55-64: 14.5% · 65+: 6.5%
- Top countries: **Israel 93.8%** · US 1.6% · Palestine 1.1% · Brazil (n/a)
- Top cities: ❓ not captured (screenshot shows Countries tab) — capture Cities tab for the ranked-city card
- Gender split: **70.4% female / 29.6% male** (provided by Ofir, 2026-07-30 — Instagram Insights)
- Followers: 30K+ (whyme section claim)

## Community survey

- >70% of surveyed community members work in tech ✅ (used site-wide)
- Survey question wording: ❓ document
- Number of respondents: ❓ document
- Collection date: ❓ document

## Community / referral bot (aggregated only — no personal data)

Live source: `GET /wa/debug/stats?key=<ADMIN_SECRET>` on the bot service
(added 2026-07-30). Snapshot 2026-07-30:

- Bot live since 2026-06-13 → **46 days** (site shows "45+")
- Users total: **549** · registered candidates (name given): **403** (site shows "400+")
- Conversations: 548 total; 548 touched in last 30 days → **18.3/day** 30-day average.
  ⚠️ every conversation row was updated within 30 days — a migration/broadcast may
  have touched `updated_at`, so treat the daily average as an upper bound; re-check
  next month when the window is organic.
- Registered community members: 1,300+ (per Ofir, 2026-07)
- Monthly registrations / referral totals: ❓
- Professional categories: currently the 6 generic ones on the Results page — replace with real bot categories
- Candidate example cards: currently ILLUSTRATIVE (marked as such on the page) — replace with real anonymized, consented profiles
- Consent status for CV sharing: only surface candidates with explicit consent

## Site placement map (don't duplicate)

- **About** → credibility only: 70%+ tech, decision-makers, 1,300+ members
- **Work** → per-video results + strip (200K+ views, 400+ link clicks, 2.3×)
- **Results** → full evidence: audience charts, campaign cards, talent network
