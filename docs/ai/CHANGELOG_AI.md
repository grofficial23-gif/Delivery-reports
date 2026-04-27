# CHANGELOG_AI.md
> Log of all AI-driven changes to PM Digest / Delivery Reports.
> Update this file at the end of every AI task that modifies source files.

---

## Format

```
## YYYY-MM-DD — <task short name>

**Task:** One-line description of the goal.

**Files changed:**
- `path/to/file` — what changed

**Reason:** Why the change was made.

**Rollback notes:** How to undo if something breaks.
```

---

## 2025-05-?? — V2 Rollback Protection

**Task:** Add `DASHBOARD_UI_VERSION` feature flag and V2 template placeholder.

**Files changed:**
- `src/delivery_reports/config.py` — added `dashboard_ui_version: str = "v1"` to `Settings`; reads `DASHBOARD_UI_VERSION` env var
- `src/delivery_reports/web_app.py` — `GET /dashboard` now selects `index.html` (v1) or `dashboard_v2.html` (v2) based on flag
- `src/delivery_reports/web/templates/dashboard_v2.html` — created minimal placeholder
- `docs/V2_ROLLBACK_AND_FLAG_PLAN.md` — created rollback plan documentation

**Reason:** Prepare safe path for V2 UI without breaking V1 production.

**Rollback notes:** Set `DASHBOARD_UI_VERSION=v1` (or remove the var) in `.env` and restart the server. V1 is unmodified.

---

## 2025-05-?? — V2 Standalone Prototype (initial)

**Task:** Create standalone V2 prototype HTML with DNA spiral, glass cards, dark/light/wave-blue themes.

**Files changed:**
- `docs/prototypes/pm_digest_v2_preview.html` — created from scratch

**Reason:** Validate V2 design before any production work.

**Rollback notes:** File is in `docs/prototypes/`, no production impact.

---

## 2025-05-?? — V2 Prototype: Background-First Architecture

**Task:** Rewrite prototype layout to background-first: canvas as full-screen layer 0, all UI floating above.

**Files changed:**
- `docs/prototypes/pm_digest_v2_preview.html` — full structural rewrite to 3-layer architecture

**Reason:** Previous version placed spiral inside a bordered card; required design has spiral as full-screen background hero.

**Rollback notes:** No production impact. Git history has previous version.

---

## 2025-05-?? — V2 Prototype: Canvas Visibility Fixes

**Task:** Fix DNA spiral not rendering after structural rewrite (race condition, low particle visibility, opaque fades).

**Files changed:**
- `docs/prototypes/pm_digest_v2_preview.html` — deferred resize/start with rAF, added ResizeObserver, increased particle alpha floors, reduced fade opacity, added debug HUD (toggle with X key)

**Reason:** Canvas showed 0×0 dimensions on initial load due to rAF race; spiral was invisible.

**Rollback notes:** No production impact.

---

## 2026-04-27 — GRACE-lite AI Documentation

**Task:** Create persistent AI context documentation suite.

**Files changed:**
- `docs/ai/PROJECT_CONTEXT.md` — created
- `docs/ai/MODULE_MAP.md` — created
- `docs/ai/DESIGN_V2_CONTRACT.md` — created
- `docs/ai/AGENT_WORKFLOW.md` — created
- `docs/ai/CHANGELOG_AI.md` — created (this file)
- `docs/ai/RAG_READY_DATA_MODEL.md` — created

**Reason:** Reduce repeated context in AI prompts; give agents a stable reference instead of re-explaining requirements.

**Rollback notes:** Documentation only. No code changed.
