# AGENT_WORKFLOW.md
> Rules for AI agents working on PM Digest / Delivery Reports.
> Follow these in every task, without exception.

---

## Core Principle

**Do not rewrite the whole project.**  
Work in small, focused, reversible patches.

---

## Task Execution Order

1. **Analyze** — read the relevant files, understand current state.
2. **Plan** — list what will be changed and why.
3. **Patch** — make the minimal change to achieve the goal.
4. **Report** — list every file changed, what changed, and how to test.

Never skip to step 3 without steps 1 and 2.

---

## Scope Rules

| Rule | Detail |
|---|---|
| One task = one file group | Prefer touching 1–3 files per task. Ask if scope grows. |
| Visual task → frontend only | Do not touch backend routes/services for visual/layout tasks. |
| Backend task → no template changes | Do not edit templates for backend-only tasks. |
| Prototype is safe | `docs/prototypes/` can be edited freely. Not production. |
| Production templates are guarded | `index.html`, `app.css`, `app.js` require explicit permission. |
| Admin/landing are separate | Never edit `admin.html` or `landing.html` for dashboard tasks. |

---

## V1 Rollback Protection

- **`index.html`, `app.css`, `app.js` are the V1 rollback.** Do not modify.
- `DASHBOARD_UI_VERSION=v1` must always work and render V1 correctly.
- Never remove or rename the `dashboard` route.
- Never break existing POST routes (`/add_note`, `/build_draft`, `/preview_report`, `/send_report`, etc.).
- If V2 is unstable, the path to revert is: set `DASHBOARD_UI_VERSION=v1` in `.env` and restart.

---

## Data Rules

- **Do not use fake or invented production metrics** in production templates.
- Static/mock data is allowed only in `docs/prototypes/` files.
- Do not hardcode user IDs, tokens, or personal Telegram handles in code.

---

## Routes & Schema

- Use existing routes when possible. Prefer extending over creating.
- **Ask before adding a new database column, table, or index.**
- Never run `DROP TABLE` or `ALTER TABLE ... DROP COLUMN` without explicit approval.
- Schema changes must be accompanied by a migration note in `CHANGELOG_AI.md`.

---

## Output Format (end of every task)

After completing a task, always output:

```
## Changed files
- path/to/file.py — what changed

## How to test
...

## Rollback
...

## Risks / limitations
...
```

---

## Forbidden Actions

- Do not run `git push`, `git reset --hard`, or any destructive git command.
- Do not install new Python packages without listing them and asking.
- Do not add external JS/CSS libraries to production templates without approval.
- Do not use `Aidentika` or medical terms anywhere (see `DESIGN_V2_CONTRACT.md`).
- Do not send user data to external services.
- Do not modify `.env` or `config.py` for visual/prototype tasks.

---

## Context Loading

When starting a new task, load relevant context files:

| Task type | Load these docs |
|---|---|
| Any task | `docs/ai/PROJECT_CONTEXT.md` |
| Backend / routes | `docs/ai/MODULE_MAP.md` |
| V2 design / prototype | `docs/ai/DESIGN_V2_CONTRACT.md` |
| Data model / schema | `docs/ai/RAG_READY_DATA_MODEL.md` |
| After making changes | Update `docs/ai/CHANGELOG_AI.md` |
