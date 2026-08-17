# AI CV Reviewer / Optimizer (V2) — /hitech/cv-review

One upload → extraction → guide review (before-scores) → optimized one-page
English CV (DOCX + PDF + text, rebuilt from scratch) → validation/repair →
after-scores → career recommendations. Code lives in the `cv_review/` package;
`pipeline.py` is the orchestrator and documents the phases.

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
- Default `gemini-3.5-flash-lite` via `GEMINI_CV_MODEL` (generateContent +
  responseSchema; NO tools — no search grounding/URL context/code execution).
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
- Retention: non-consented reviews purge after `CV_REVIEW_RETENTION_DAYS`
  (default 180); `talent_pool_consent` comes from the upload-form checkbox.

## Testing / evaluation
- `./venv/bin/python -m pytest tests/` — security fixtures + enforcement
  tests (this feature is the exception to the no-tests convention; the V2
  spec requires them).
- `./venv/bin/python scripts/cv_eval.py` — live eval of the synthetic CVs in
  `tests/fixtures/eval/` through the real pipeline; artifacts land in
  `artifacts/cv_eval/` (read the generated CVs, not just the scores).

## Env vars (see .env.example)
`GEMINI_API_KEY` (paid project), `GEMINI_CV_MODEL`, `CV_REVIEW_PASSWORD`,
`CV_REVIEW_RETENTION_DAYS`, optional `GOOGLE_DRIVE_CREDENTIALS_JSON` +
`GOOGLE_DRIVE_CV_FOLDER_ID`. Procfile timeout is 300s for the multi-call
pipeline.
