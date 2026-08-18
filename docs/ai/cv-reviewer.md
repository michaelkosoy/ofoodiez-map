# AI CV Reviewer / Optimizer (V2) — /hitech/cv-review

One upload → extraction → guide review (before-scores) → optimized one-page
English CV (DOCX + PDF + text, rebuilt from scratch) → validation/repair →
after-scores → career recommendations. Code lives in the `cv_review/` package;
`pipeline.py` is the orchestrator and documents the phases.

## Runtime shape
- **Open to the public** since 2026-08-18 — no password. The shared-password
  gate is still in the code but bypassed; set `CV_REVIEW_PASSWORD_ENABLED=1` to
  re-close it (same dormant-gate pattern as `/hitech/cv-guide/full`).
- **Spend guards**: 5 reviews/hour per IP plus a whole-site cap of
  `CV_REVIEW_DAILY_CAP` reviews per rolling 24h (default 200 ≈ $7/day at
  today's ~$0.034/review; 0 = unlimited). Both answer 429 with a friendly
  message.
- **Consent is mandatory**: no consent → 400, no review. The checkbox links to
  `/hitech/cv-review/terms` (`app/templates/legal/cv_review_terms.html`),
  written to mirror the referrals-bot ToS.
- **Async + polling**: `POST /api/hitech/cv-review` starts a background thread
  and returns `{status: processing, review_id}`; the page polls
  `/api/hitech/cv-review/<id>/status`. This is not optional — a full review
  takes 30–90s and Cloudflare cuts origin responses at ~100s, swallowing the
  body, which is exactly how a working pipeline looked like a generic
  "something went wrong" to the user. Failures are stored on the row and
  surfaced verbatim through the status endpoint.

## Output guarantees
- **True one-pager**: `pdf_writer` measures the story and renders at the
  largest type scale that fits one page, then spreads leftover height across
  the section gaps — thin CVs fill the page, long CVs compress. `docx_writer`
  mirrors the template with a volume-based font preset (Word gives us no
  layout engine to measure).
- **Content floor** (`validators.validate_content_floor` +
  `restore_from_canonical`): the optimizer can never return a gutted CV. A
  repair round that deletes most bullets is discarded; missing
  experience/education/projects/extras/summary/links are restored verbatim
  (address-scrubbed) from the canonical extraction; unevidenced numbers
  degrade to `[X]` instead of deleting the bullet.
- **Scores only improve or hold**: the after-critic receives the before-scores
  as an explicit anchor and the payload floors after at before. Two gradings
  of the same preserved evidence differing by a few points is judge noise, not
  a regression to show a candidate.
- **Presentation polish** (`render_common.polish_cv`) runs once before all
  renderers: link labels (LinkedIn/GitHub/Portfolio), Title-Case headings
  (acronyms kept), merging an entry's split attribute lines so "Military
  Service" isn't a pile of one-word bullets, one-line degrees, a summary
  trimmed to ≤42 words at a sentence boundary, and normalizing glyphs the
  PDF's standard fonts can't draw (U+2011 etc. rendered as black boxes).
- **Section order is a product decision** (Ofir's, 2026-08-18): Summary →
  Experience → Projects → Education → extras → **Skills last**, and the skills
  list is NOT bold (only its group label) — technologies stay emphasized
  inside the experience bullets, which is where a screener reads them. Change
  it in all three renderers together (`render_common.cv_to_text`,
  `pdf_writer`, `docx_writer`) or the three artifacts drift apart.

### Hebrew in the PDF
reportlab's built-in fonts have no Hebrew glyphs and no bidi engine, so Hebrew
(typically the candidate's name, sometimes a Languages line) used to render as
black boxes. Now: `cv_review/fonts/NotoSansHebrew-{Regular,Bold}.ttf` (OFL,
42 KB each, license in the same folder) is registered at import, and
`pdf_writer._hebrew_aware()` renders Hebrew runs in that font after reordering
them to visual order with `python-bidi`. Latin text keeps Helvetica, so the
approved look is unchanged. If the font ever fails to load, `HEBREW_READY` goes
false and reviews still run (Hebrew degrades to boxes rather than erroring).
The DOCX and text exports keep logical order — Word applies bidi itself.

## Cost (measured, not estimated)
Baseline from 15 completed prod reviews (2026-08-17/18) on flash-lite only:
**52,877 input + 7,522 output tokens, 5.5 calls, 25s, $0.0347 per review.**
Same workload priced at other tiers: 3.1-flash-lite $0.025 · **hybrid
(rewrite on 3.7-flash) $0.050** · all-3.7-flash $0.068 · 3.5-flash $0.147 ·
3.1-pro $0.196. Guide-prefix caching is expected to take the hybrid to
~$0.042. Per-review model/tokens/cost/duration are recorded in
`cv_reviews.usage` and shown in admin → CV Reviews — check real numbers there
after any model change rather than trusting these projections.

## Invariants (enforced by validators + tests, not just prompts)
- **Candidate name** comes from the CV only, preserved EXACTLY (never the
  logged-in account's name, never shortened/corrected/invented). Low
  confidence → the UI asks the user to confirm before the CV is generated.
- **Residential privacy**: the optimized CV never carries anything more
  precise than a city. Street/number/apartment/ZIP are redacted before the
  optimizer runs and re-checked on the final text (`validators.py`).
- **Evidence discipline**: no skill, number or JD keyword enters the CV
  without evidence in the uploaded document; missing metrics become
  `[placeholders]`. JD requirements without evidence go to career
  recommendations only.
- **Wording**: absence of evidence is phrased "לא נראה בקורות החיים" /
  "isn't evidenced in your CV" — never "you don't know X".
- **Job input is TEXT only**: job URLs are rejected (`jobspec.py`), incidental
  URLs inside pasted JDs are stripped, and nothing is ever fetched.
- **Hostile uploads**: DOCX parses in a sandboxed one-shot child process with
  a scrubbed env (no secrets), rlimits and a kill timeout (`sandbox.py` +
  `docx_worker.py` — ZIP-bomb/ZIP-slip/macro/OLE/ActiveX/XML-DTD defenses).
  PDFs are never parsed in-process (Gemini reads them upstream). The final
  DOCX is generated fresh (`docx_writer.py`) and package-inspected
  (`docx_inspect.py`) — nothing from the upload is copied through.
- **The uploaded original** is stored labeled RAW/UNTRUSTED (audit only);
  the sanitized reconstruction is the main document everywhere, including
  the admin default download.

## Model & cost
- **Hybrid, per step** (`gemini.STEP_MODELS`): extraction and both critics run
  on `gemini-3.5-flash-lite`; the REWRITE and its repairs run on
  `gemini-3.7-flash`, because that is the only step whose prose the candidate
  reads. Override any step with `GEMINI_CV_MODEL_<STEP>` (OPTIMIZE, REPAIR,
  EXTRACT, CRITIC, TRANSLATE), change the base with `GEMINI_CV_MODEL`, or set
  `GEMINI_CV_HYBRID=off` to put everything back on one model. A per-step model
  that the API key can't use falls back to the base model for the rest of the
  process instead of failing reviews.
- **Guide-first prompts**: the ~18k-token guide is emitted by
  `prompts.guide_prefix()` as the byte-identical LEADING block of every prompt
  that carries it, so Gemini's implicit context caching charges the repeat
  copies at ~1/10 the input rate. Anything call-specific must come AFTER that
  block or caching stops hitting.
- generateContent + responseSchema; NO tools — no search grounding, URL
  context or code execution.
- ~5 calls/review (extract, critic×2, optimize, +repairs when needed);
  per-review tokens/cost recorded in `cv_reviews.usage` (no prompts logged).
- Don't swap models on vibes: `scripts/cv_eval.py` is the judge — compare
  violations, repair counts, scores, runtime and cost before upgrading.
- **PAID-tier Google AI project required in production** (personal data — the
  paid data terms, never free-tier).

## Storage
- `cv_reviews` table (auto-creates): metadata (candidate name/email/phone are
  searchable in admin → CV Reviews), canonical extraction, result payload,
  usage, and the three artifacts as blobs (prod disk is ephemeral — DB is the
  durable store). UUIDs are the security identifiers; candidate names are
  display labels only (`storage.sanitize_name`).
- Optional Drive mirror (`GOOGLE_DRIVE_CREDENTIALS_JSON` +
  `GOOGLE_DRIVE_CV_FOLDER_ID`): `<folder>/<owner>/<review_uuid>/…`, never
  shared publicly.
- Retention: incomplete/failed runs purge after 7 days; completed reviews
  without talent-pool consent (legacy rows from before consent was mandatory)
  purge after `CV_REVIEW_RETENTION_DAYS` (default 180); completed + consented
  reviews are kept until a deletion request.

## Testing / evaluation
- `./venv/bin/python -m pytest tests/` — security fixtures + enforcement
  tests (this feature is the exception to the no-tests convention; the V2
  spec requires them).
- `./venv/bin/python scripts/cv_eval.py` — live eval of the synthetic CVs in
  `tests/fixtures/eval/` through the real pipeline; artifacts land in
  `artifacts/cv_eval/` (read the generated CVs, not just the scores).

## Env vars (see .env.example)
`GEMINI_API_KEY` (paid project), `GEMINI_CV_MODEL`, `CV_REVIEW_PASSWORD`,
`CV_REVIEW_RETENTION_DAYS`, `CV_REVIEW_DAILY_CAP`,
`CV_REVIEW_PASSWORD_ENABLED` (unset = public), optional
`GOOGLE_DRIVE_CREDENTIALS_JSON` + `GOOGLE_DRIVE_CV_FOLDER_ID`. Procfile timeout is 300s for the multi-call
pipeline.
