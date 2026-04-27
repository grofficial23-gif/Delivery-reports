# PROJECT_CONTEXT.md
> AI persistent context — load this before any task on PM Digest / Delivery Reports.

---

## Product

**Name:** PM Digest / Delivery Reports  
**Short brand name:** DIGEST or PM DIGEST  
**Internal code name:** delivery_reports  

**What it is:**  
A Telegram bot + Mini App for Project, Product, and Delivery managers.  
It collects raw data (notes, voice, tasks, templates) and converts them into structured delivery reports.

---

## Core MVP Workflow

```
User inputs (notes / voice memos / task exports / templates)
    ↓
Structured draft  (assembled by bot or Mini App)
    ↓
Preview in Mini App (user reviews and edits)
    ↓
Finalize → send to self in Telegram / copy / export
```

---

## Current Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python), served via uvicorn |
| Database | SQLite — `sqlite3` module, Repository pattern |
| Telegram bot | `python-telegram-bot` (or aiogram) |
| Payments | Telegram Stars (`LabeledPrice`) |
| Web / Mini App | Jinja2 templates, vanilla JS, CSS custom properties |
| Config | `.env` via `python-dotenv`, `Settings` dataclass |
| Feature flags | `DASHBOARD_UI_VERSION=v1|v2` (env var) |
| Auth | Telegram Mini App `initData` hash validation |

---

## Subscription Plans

| Plan | Key features |
|---|---|
| FREE | limited notes/month, basic report |
| PRO | unlimited notes, voice, drafts, export |
| TEAM | multi-user, shared projects, admin panel |

Payments via Telegram Stars. Plans stored in `user_plan` field on User.

---

## Security Rules

- **Local-first processing** — user data must not be sent to third-party AI/cloud by default.
- Telegram auth only — no email/password registration.
- `is_super_admin` controlled via `SUPER_ADMIN_USERNAMES` env var, not DB flag.
- Admin panel is separate route (`/admin`), not part of Mini App.
- No external analytics SDKs in the Mini App.
- Banking-grade sensitivity: treat all note/report content as private.

---

## Brand Rules (MANDATORY for all AI tasks)

| Rule | Detail |
|---|---|
| Allowed brand names | PM DIGEST, DIGEST, Delivery Reports |
| Forbidden brand name | Aidentika (never use in UI, code comments, docs, copy) |
| Forbidden terms | Patient, Medical, Surgical, Biometrics, Neuro, Healthcare, Clinical |
| Product context | This is a **PM reporting tool**, not a health/medical product |
| Subtitle | DELIVERY REPORTS |

---

## Key People

- `pm_vibe` — super admin username (Telegram handle)

---

## Related AI docs

| File | Purpose |
|---|---|
| `docs/ai/MODULE_MAP.md` | What each file does, which routes it owns |
| `docs/ai/DESIGN_V2_CONTRACT.md` | V2 visual design rules, theme tokens, layout law |
| `docs/ai/AGENT_WORKFLOW.md` | How AI agents must behave on this project |
| `docs/ai/CHANGELOG_AI.md` | Log of AI-driven changes |
| `docs/ai/RAG_READY_DATA_MODEL.md` | Data entities for future RAG / search |
