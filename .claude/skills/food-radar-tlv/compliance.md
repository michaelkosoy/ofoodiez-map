# Compliance — food-radar-tlv

These rules are mandatory. When in doubt, do less.

## Allowed
- Use **public information** or **authenticated APIs the user has permission to use**.
- For social posts, store only: **public URL**, **public handle / page name**, **caption excerpt**,
  **date**, and the **reason it is relevant**.
- Use Tavily **indexed public search** when direct social access is unavailable.

## Not allowed
- Do **not** scrape private pages.
- Do **not** bypass login walls, paywalls, CAPTCHAs, rate limits, or robots restrictions.
- Do **not** impersonate users.
- Do **not** DM anyone.
- Do **not** make reservations.
- Do **not** apply to jobs.
- Do **not** contact venues.
- Do **not** collect private personal data.

## Data minimization
- Keep only what is needed to verify and re-find a public signal (the fields above + proof URLs).
- Do not aggregate personal profiles or build dossiers on individuals.

## Proof rule
- If a real proof URL cannot be obtained from an actual tool result, **do not output the item.**
- Never invent, autocomplete, or guess URLs or dates.

## Connectors
- Use official platform APIs only if **credentials and permissions exist**.
- Use Apify MCP or similar connectors **only if available** and **only for public / allowed data**.
- The skill's default and safe path is **Tavily indexed public search**.
