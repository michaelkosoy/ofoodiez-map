# Instagram DM & Comment Automation — Handover Context

This document provides a comprehensive state description of the Instagram Automation service setup, architecture, credentials, verified flows, and current Meta/Facebook Developer Portal constraints. Use this as a direct bootstrapper for a fresh agent session.

---

## 🔑 Meta App & API Configuration

These credentials are saved locally in the [.env](file:///Users/ofirlazarov/Documents/ofoodiez/website/.env) file.

- **Meta App ID**: `2091558228453268`
- **Meta App Secret**: `0774dcb27d7906596226a3f66db7f74e`
- **Webhook Verify Token**: `ofoodiez_ig_verify_2025` (configured in [config.py](file:///Users/ofirlazarov/Documents/ofoodiez/website/instagram_automation/config.py))
- **Production Webhook URL**: `https://ofoodiez.com/ig/webhook` (or Render host `https://ofoodiez-map.onrender.com/ig/webhook`)
- **API Version**: `v25.0`
- **Required OAuth Scopes**: `instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments`

---

## ⚙️ Facebook Developer Portal State & Limitations

### 1. App Mode & Webhook Constraints
- **App Status**: Currently configured in the Meta App dashboard.
- **Webhook Subscriptions**: 
  - Subscribed to the `comments` field (tested and verified at API `v25.0`).
  - Subscribed to the `live_comments` field (tested and verified at API `v25.0`).
  - Subscribed to the `messages` / `messaging_postbacks` fields.
- **Constraints (Important)**:
  - For webhooks to trigger in **Development Mode**, the account making the interaction (commenting or messaging) **MUST** be explicitly added as a developer, tester, or administrator role in the Meta App Roles dashboard.
  - The business account target (`@ofoodiez`) must be a **Business or Creator Account** and must be linked to a Facebook Page managed under the same Facebook Developer Account.
  - To receive comments and messages from the general public, the App must be promoted to **Live Mode (Published)**, and requests for the specific permissions (`instagram_business_manage_messages`, `instagram_business_manage_comments`) must pass App Review.

---

## 🛠️ Implemented Architecture & Features

The Instagram Automation service is structured inside the [instagram_automation/](file:///Users/ofirlazarov/Documents/ofoodiez/website/instagram_automation/) folder:

1. **Dashboard & UI**:
   - Logins are routed via `/ig/`. Bypassing OAuth locally is supported via **Mock Developer Login** (injects a simulated local user thread).
   - Glassmorphic Inbox UI at `/ig/inbox` featuring 3-panes (threads list on left, chat timeline with 24-hour expiration timer in middle, and contact details/tags editor on right).
   - Automation Builder at `/ig/automations` supporting text responses, button templates, and quick replies.
2. **Video Discovery**:
   - Integrates a visual media/reels picker inside the automation creator.
   - Allows users to link a comment keyword automation to a **Specific Post/Video** (via `media_id` matching in `automations.py`) rather than trigger globally for all posts.
3. **Database & Storage**:
   - Path: [instagram_automation.db](file:///Users/ofirlazarov/Documents/ofoodiez/website/instagram_automation.db) (SQLite database in website root).
   - Keeps track of:
     - `User`: Meta user tokens and IDs.
     - `Contact`: Instagram profiles, custom tags, email, and phone numbers.
     - `MessageLog`: History of sent and received messages.
     - `Automation`: Keywords, trigger types, matching rules, and action payloads.

---

## 🧪 Local Dev & Verification Tools

### How to Run Locally
1. Start the Flask application:
   ```bash
   venv/bin/python3 app.py
   ```
   (Runs on [http://localhost:5000/ig/](http://localhost:5000/ig/))
2. Open the browser to [http://localhost:5000/ig/](http://localhost:5000/ig/) and click the **Mock Developer Login** button to populate mock contacts, inbox threads, and play with the dashboard.

### Verification Scripts
Two pre-built automated scripts are available in the [scripts/](file:///Users/ofirlazarov/Documents/ofoodiez/website/scripts/) directory to test the engine without making actual calls to Meta APIs:
- **[verify_ig.py](file:///Users/ofirlazarov/Documents/ofoodiez/website/scripts/verify_ig.py)**: Simulates the E2E flow of incoming comment triggers, creation of database contacts, messaging timeouts, and chained button postbacks.
- **[verify_media_automations.py](file:///Users/ofirlazarov/Documents/ofoodiez/website/scripts/verify_media_automations.py)**: Simulates and validates post-specific automation triggers, ensuring keywords only fire on target `media_id` matches.

To execute them:
```bash
venv/bin/python3 scripts/verify_ig.py
venv/bin/python3 scripts/verify_media_automations.py
```

---

## 🚀 Deployment

- The workspace is connected to the GitHub repository: `git@github.com:michaelkosoy/ofoodiez-map.git`.
- Pushes to the `main` branch trigger an automatic deploy on **Render** linked to [ofoodiez.com](https://ofoodiez.com/).
