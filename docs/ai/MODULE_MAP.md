# MODULE_MAP.md
> Map of current source files and their responsibilities.
> Before editing any file, check its "Do not touch unless" rule.

---

## Backend

### `src/delivery_reports/web_app.py`
- **Purpose:** FastAPI application — all HTTP routes for the Mini App and web dashboard.
- **Owns:**
  - `GET /dashboard` — renders dashboard template (V1 or V2 via feature flag)
  - `GET /admin` — admin panel
  - `GET /landing` — landing page
  - `POST /add_note` — create note
  - `POST /build_draft` — assemble draft from notes
  - `POST /preview_report` — render draft preview
  - `POST /send_report` — send finalized report to Telegram
  - `POST /finalize_report` — mark report as final
  - `GET /history` — report history
  - `POST /resolve_inbox` — inbox item resolution
  - `GET/POST /tasks` — task management
  - `GET/POST /admin/*` — admin actions
  - `GET/POST /subscription/*` — plan upgrade, Telegram Stars payment initiation
- **Do not touch unless:** adding a new route, or the task explicitly involves backend logic.
- **Related:** `config.py`, `repository.py`, `admin_service.py`, `subscription_service.py`

---

### `src/delivery_reports/config.py`
- **Purpose:** Centralized settings loaded from `.env`. Single `Settings` dataclass.
- **Key fields:**
  - `telegram_bot_token`
  - `web_session_secret`
  - `dashboard_ui_version` — `"v1"` or `"v2"` (controls which template `/dashboard` renders)
  - `super_admin_usernames` — frozenset, from `SUPER_ADMIN_USERNAMES` env var
  - `public_web_app_url`
- **Do not touch unless:** adding a new config value or feature flag.

---

### `src/delivery_reports/database.py` (or `repository.py`)
- **Purpose:** SQLite database access layer. `Repository` class with typed methods. `Database` class manages schema and connection.
- **Owns:** all SQL queries — notes, drafts, reports, tasks, users, subscriptions.
- **Do not touch unless:** schema change or new data operation. **Always ask before schema changes.**

---

### `src/delivery_reports/admin_service.py`
- **Purpose:** Business logic for admin operations (user list, plan override, stats).
- **Do not touch unless:** admin feature task.

---

### `src/delivery_reports/subscription_service.py`
- **Purpose:** Plan validation, Telegram Stars invoice creation, plan upgrade logic.
- **Do not touch unless:** subscription/payment feature task.

---

### `src/delivery_reports/transcription_service.py` (if present)
- **Purpose:** Voice memo transcription pipeline.
- **Do not touch unless:** voice/transcription task.

---

### Bot handlers (`src/delivery_reports/bot/` or inline in `main.py`)
- **Purpose:** `python-telegram-bot` handlers for commands, inline buttons, voice messages.
- **Do not touch unless:** bot command or Telegram interaction task.

---

## Frontend Templates

### `src/delivery_reports/web/templates/index.html`
- **Purpose:** V1 dashboard — current production Mini App UI.
- **Status:** ✅ Production. **Do not modify.** This is the V1 rollback point.
- **Rendered by:** `GET /dashboard` when `DASHBOARD_UI_VERSION=v1`

### `src/delivery_reports/web/templates/dashboard_v2.html`
- **Purpose:** V2 dashboard placeholder. Currently a minimal shell.
- **Rendered by:** `GET /dashboard` when `DASHBOARD_UI_VERSION=v2`
- **Status:** Placeholder — V2 design will be applied from prototype once approved.

### `src/delivery_reports/web/templates/admin.html`
- **Purpose:** Admin panel template.
- **Do not touch unless:** admin task. Never merge with dashboard templates.

### `src/delivery_reports/web/templates/landing.html`
- **Purpose:** Public landing page.
- **Do not touch unless:** landing page task. Separate design system.

---

## Static Assets

### `src/delivery_reports/web/static/app.css`
- **Purpose:** V1 production stylesheet. CSS custom properties for theming.
- **Do not touch unless:** V1 visual bug fix. Do not add V2 styles here.

### `src/delivery_reports/web/static/app.js`
- **Purpose:** V1 production JavaScript (UI logic, Telegram WebApp API calls).
- **Do not touch unless:** V1 logic bug fix.

---

## Prototypes & Docs (not deployed)

### `docs/prototypes/pm_digest_v2_preview.html`
- **Purpose:** Standalone V2 design prototype. Self-contained HTML/CSS/JS.
- **Status:** Active development. Safe to edit freely — no production impact.
- **See:** `docs/ai/DESIGN_V2_CONTRACT.md` for visual rules.

### `docs/V2_ROLLBACK_AND_FLAG_PLAN.md`
- **Purpose:** Rollback strategy documentation. How to switch V1↔V2.

---

## Feature Flag: DASHBOARD_UI_VERSION

```
DASHBOARD_UI_VERSION=v1   → serves index.html     (default, safe)
DASHBOARD_UI_VERSION=v2   → serves dashboard_v2.html
```

Set in `.env`. Read in `config.py → Settings.dashboard_ui_version`.  
Applied in `web_app.py → GET /dashboard`.
