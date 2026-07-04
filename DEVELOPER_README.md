# Developer README - External Integrations

This document tracks all external services, APIs, and platforms integrated into the Ofoodiez Map application. 

**Note to developers:** If the owner is marked as `[Michael / Ofir - Please update]`, please fill in the correct owner.

---

## 1. Hosting & Infrastructure

### Render
* **Usage:** Hosts the main Flask web application and the Instagram webhook endpoint (`https://ofoodiez-map.onrender.com`). Deployment is automated via GitHub pushes to the `main` branch.
* **Owner:** Michael Kosoy (based on deployment documentation paths)

### Cloudflare
* **Usage:** Provides CDN services (such as serving Font Awesome) and likely handles DNS / SSL for the main domain (`ofoodiez.com`).
* **Owner:** [Michael / Ofir - Please update]

### Supabase
* **Usage:** Infrastructure for database / authentication. (Note: Supabase agents skill is present in the repository, used for future or current database needs).
* **Owner:** [Michael / Ofir - Please update]

---

## 2. Communications & Email

### Formspree (Email Forwarding)
* **Usage:** Free email API service used to handle form submissions and forward emails.
* **Forwarding Address:** `ofir.lazarov@gmail.com`
* **Owner:** Ofir Lazarov

### ImprovMX (Domain Email Forwarding)
* **Usage:** Domain email forwarding service used to route emails sent to `contact@ofoodiez.com` to the personal email address.
* **Forwarding Address:** `ofir.lazarov@gmail.com`
* **Owner:** Ofir Lazarov

### Telegram Bot API
* **Usage:** Used for the Telegram Bot Content Management system to process and manage popups or happy hour places.
* **Owner:** [Michael / Ofir - Please update]

### Twilio (WhatsApp Referral Bot)
* **Usage:** Powers the WhatsApp referral-link bot at `/wa/webhook`. Inbound messages are verified against the Twilio account Auth Token (`TWILIO_AUTH_TOKEN`) via `RequestValidator`, using the pinned `TWILIO_WEBHOOK_URL`. Replies are synchronous TwiML (no outbound REST calls in MVP). Full design in `docs/whatsapp-referral-bot-plan.md`.
* **Owner:** [Michael / Ofir - Please update]

---

## 3. Data & Content

### Google Maps API
* **Usage:** Renders the interactive map on the website. Requires `GOOGLE_MAPS_API_KEY`.
* **Owner:** [Michael / Ofir - Please update]

### Google Sheets API
* **Usage:** Acts as a data source for the application (e.g., places, happy hours). Requires `SHEET_ID`.
* **Owner:** [Michael / Ofir - Please update]

---

## 4. Social & Automation

### Meta / Instagram Graph API
* **Usage:** Instagram automation features, DM responses, and webhooks. Requires a Meta App setup with `META_APP_ID`, `META_APP_SECRET`, and a `WEBHOOK_VERIFY_TOKEN`.
* **Owner:** [Michael / Ofir - Please update]

---

## 5. Artificial Intelligence

### Google Gemini API
* **Usage:** Provides AI capabilities (like parsing and generating content) for the Telegram Bot.
* **Owner:** [Michael / Ofir - Please update]

---

## Adding a New Integration

When adding a new integration to the codebase:
1. Add the necessary API keys to `.env.example`
2. Update this document with the **Usage** and **Owner**.
