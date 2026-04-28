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

---

## 2026-04-28 — v2.23.1: Mobile polish + asset cache busting (Step 25)

**Task:** Fix V2 mobile layout issues and introduce automatic cache busting for all V2 static assets.

**Files changed:**
- `src/delivery_reports/config.py` — bumped default `app_version` to `"v2.23.1"` (both dataclass default and `load_settings` fallback); added versioning discipline comment (patch/minor/major semantics).
- `src/delivery_reports/web/static/v2/dashboard_v2.css` — added `PMD:V2:MOBILE_POLISH` block: CTA buttons get `height:auto; min-height:52px; line-height:1.2; word-break:normal` at ≤760px; topnav progressively hides non-critical elements (days-left, "←Лендинг", plan badge) at ≤760px/≤480px; user chip collapses to avatar-only at ≤480px; ≤360px minimum survival rules.
- `src/delivery_reports/web/static/v2/landing_v2.css` — added `PMD:V2:LANDING_MOBILE_NAV` block: `.s1-open-btn` hardened with `flex-shrink:0!important`; `.s1-theme-row` hidden at ≤480px so the "Открыть бота" CTA is always the only nav action on phones.
- `src/delivery_reports/web/templates/dashboard_v2.html` — CSS/JS `<link>`/`<script>` tags now carry `?v={{ app_version }}` query strings.
- `src/delivery_reports/web/templates/landing_v2.html` — same cache-busting query strings.
- `src/delivery_reports/web/templates/admin.html` — same cache-busting query strings for both V2 CSS and both V2 JS script tags.

**Reason:** Telegram Mini App and CDN/Render caches serve stale CSS after deploys. A version query string forces a cache miss on every new build. The mobile layout fixes resolve CTA text clipping and topnav overflow at 390px viewport.

**Rollback notes:** Revert `app_version` to `"v2.23.0"` in `config.py` and remove the `?v=` suffixes from the three templates. CSS blocks are clearly delimited and can be removed independently.
