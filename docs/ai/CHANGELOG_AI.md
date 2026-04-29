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

## 2026-04-28 — v2.24.0: Project recognition + clean report output (Step 25)

**Task:** Make report quality demo-ready. The 9-block test message had three failures: every block was tagged "Не уверен", neutral mentions of words like "блокер" caused false-positive blocker classification, and synthetic prefixes ("вопрос — Вопрос по Bank Dashboard:") leaked into bullets. This step fixes all three.

**Files changed:**
- `src/delivery_reports/services/long_update_split.py` — replaced substring keyword matching with **strict regex-driven `_classify_intent`**. Strong start patterns now require `:` / `-` / `—` / preposition after the marker; e.g. `^Блокер:`, `^Блокер по X`, `^Риск на`. Anywhere-in-sentence verbs are word-boundary aware (`\bне\s+можем\s+продолжить\b`, etc.). Neutral mentions of "сделано / план / риск / блокер" inside ordinary sentences NO LONGER trigger any intent. Added `_is_project_only_sentence` to drop pure project-label noise like "Проект: Delivery." Improved `_detect_project_by_alias`: phrase aliases ("Bank Dashboard") score before single-word aliases ("Bank"), single-word aliases under 3 chars are skipped (no false matches on "ID"/"QA"). Restricted item merging to `{done, plan, other}` so blockers/risks/decisions/questions get dedicated bullets.
- `src/delivery_reports/services/parsing.py` — `_split_by_intent` unstructured path now skips metadata lines (`Проект:`, `Эпик:`, …), preventing them from becoming bullets. New `_strip_leading_project_intro(text, projects)` strips `"По <known-project-or-alias>"` from the start of voice-dictated atoms. `_atomic_to_block` pre-cleans the body via `clean_report_item_text` BEFORE injecting our synthetic prefix, so the stored text holds only ONE marker (no "блокер — Блокер по …" duplication).
- `src/delivery_reports/services/report_text_cleaner.py` — **NEW** pure module. `clean_report_item_text(text, *, project_name=None, intent_kind=None)` strips synthetic prefixes ("вопрос —", "блокер —", "решение —"), user-typed labels ("Блокер по X:", "Что сделано:", "План на завтра:"), project-switch intros ("Теперь по X:", "Касательно X:", "Дальше по X:"), and pure project-label lines ("Проект: Delivery."). Iterates until stable; capitalizes first letter; returns "" for empty / project-only input.
- `src/delivery_reports/services/draft_builder.py` — new emoji section format: `📌 <Project>` / `✅ Что сделано` / `◆ Решение` / `🧭 План` / `⚠️ Риски` / `❓ Вопросы` / `⛔ Блокеры` / `📥 Нужно уточнить проект`. Empty sections are skipped entirely (no `- нет` filler). Bullets use `•` prefix. New routing helpers `_route_done_lines` (splits done_text into done/decision/question by prefix) and `_route_risk_lines` (splits risk_text into risk/blocker). Every bullet runs through `_clean_items` → `clean_report_item_text` before display. `risk_focus` style still places blockers/risks before plan; `team_examples` retains its original layout but applies cleaning. `build_weekly_summary` updated to consume the new buckets.
- `src/delivery_reports/services/note_capture.py` — `render_saved_notes_message` now shows **intent badge + project · cleaned preview** per block instead of the old "Не уверен / Сохранено" pattern. Russian-correct pluralization for "блок/блока/блоков". `short_summary_line` runs the cleaner. New `_project_display` swaps to "📥 Нужно уточнить проект" only when the resolution sentinel ("" / "Не уверен") is present, preserving any explicit project name.
- `src/delivery_reports/config.py` — bumped `app_version` to `"v2.24.0"` (minor: visible product feature).
- `tests/test_report_quality.py` — **NEW** 27 end-to-end tests: alias recognition for Delivery Reports / Bank Dashboard / BONUS-2055 / MCC / ГТС / МФС / Антифрод; intent strictness (neutral word lists are not blocker, explicit `Блокер: …` / `Риск: …` / `План: …` / `Вопрос: …` / `Решение: …` are recognized); `clean_report_item_text` regression suite (synthetic prefix stripping, user-typed labels, project-only line drops, idempotency); final-draft hygiene (no `Вопрос — Вопрос`, no `- Проект: …` bullets, unknown projects route to the inbox section, recognized projects get `📌` emoji).
- `tests/test_draft_builder.py` — updated 3 existing tests to assert the new emoji section format (`✅ Что сделано`, `🧭 План`, `⚠️ Риски`) and `•` bullet prefix; the empty-risk filler `- нет` is no longer rendered.
- `scripts/seed_demo_aliases.py` — **NEW** idempotent helper. Run `python -m scripts.seed_demo_aliases <owner_user_id>` to ensure Delivery Reports / Bank Dashboard / Внедрение категорийного кэшбэка (BONUS-2055) projects exist with their demo aliases. Uses `repository.upsert_project`; merges with any existing aliases; never deletes data; no schema change.

**Reason:** Hardening report quality before tomorrow's demo. The system must turn a long voice/text monolog into a project-first structured daily report without false blockers, without duplicated section labels, and without "Не уверен" appearing for projects that have aliases.

**Rollback notes:** Schema unchanged. To revert: restore the old keyword-substring `_classify_intent` in `long_update_split.py`, remove `report_text_cleaner.py`, restore the prior `_render_project_block` in `draft_builder.py`, and revert `config.py` to `v2.23.2`. Existing notes in the DB remain readable; only rendering output differs.

### How to add demo aliases

The `Project.aliases` column already supports any list of strings; no schema change is needed.

1. **Easy path (recommended)** — run the seeder for your Telegram user id:

   ```bash
   python -m scripts.seed_demo_aliases 123456789
   ```

   It merges the canonical demo aliases with whatever you already have. Idempotent: safe to re-run after each deploy.

2. **Manual path** — edit `scripts/seed_demo_aliases.py:DEMO_PROJECTS` to add your own projects, then re-run the script.

3. **Programmatic path** — call `repository.upsert_project(name="…", aliases=[…], …, owner_user_id=…)` from any boot/admin code.

---

## 2026-04-28 — v2.24.1: Manual project binding + template-driven drafts (Step 27)

**Task:** Three demo-blockers: (1) inbox cards had no clear way to bind a note to a project, (2) numeric project codes like "2055" weren't recognized, (3) the four templates produced almost identical drafts.

**Files changed:**
- `src/delivery_reports/web/templates/dashboard_v2.html` — every inbox card (visible + collapsed) now renders a `POST /inbox/{id}/resolve` form with a `<select name="project_name">` populated from `projects` plus a "Привязать" button. Helper text explains the value. Existing candidate buttons remain when present. Existing `#inbox` redirect preserved.
- `src/delivery_reports/web/static/v2/dashboard_v2.css` — added `PMD:V2:INBOX_BIND` styles for the new bind form (label, select, button, mobile stacking).
- `src/delivery_reports/services/draft_builder.py` — `_render_project_block` now picks distinct section orders per style: `standard` (full picture), `concise` (trimmed: blockers, done, plan, risks only), `risk_focus` (blockers/risks/decisions/done/plan/questions). `_resolve_status_line` accepts `question_items` so the executive verdict "Требует внимания" fires when blockers, risks, or open questions exist.
- `src/delivery_reports/services/report_presenter.py` — `limit_section_items` extended to all section keys (`done/plan/risk/blocker/decision/question`); concise caps stay tight (done≤2, others≤1) and the overflow trailer reads "… ещё N пункт(а)".
- `src/delivery_reports/config.py` — `app_version` v2.24.0 → v2.24.1 (patch: UX + visible template differences, no schema or routes touched).
- `scripts/seed_demo_aliases.py` — extended BONUS-2055 alias list with "2055", "категорийный кешбэк", "High Risk Visa", "справочники".
- `tests/test_web_app.py` — 2 new tests: V2 inbox card renders the bind form with project options ("Delivery Reports", "DC701"); `POST /inbox/{id}/resolve` still binds the note and redirects to `#inbox`.
- `tests/test_report_quality.py` — 1 new test: numeric alias "2055" maps to the cashback project.
- `tests/test_draft_builder.py` — 3 new tests: standard vs executive draft outputs differ; concise mode trims long sections and shows "ещё"; risk_focus places blockers/risks before done with "Требует внимания" status.

**Reason:** Make report quality demo-ready. Users now have a one-click manual override when auto-binding fails, numeric codes resolve correctly, and switching templates in the dashboard produces a visibly different report.

**Rollback notes:** No DB / route / schema changes. To revert visually: restore the previous `_render_project_block` body and `dashboard_v2.html` inbox-card markup; bump `app_version` back to v2.24.0.

---

## 2026-04-28 — v2.24.2: Guided MVP polish (Step 28)

**Task:** New users found the workflow hard to follow: dark/wave themes washed out the draft, the inbox bind form wasn't obvious, template names had no meaning, "Executive style" was English-only, and there was no quick "how to" guide.

**Files changed:**
- `src/delivery_reports/web/static/v2/dashboard_v2.css` — added `PMD:V2:DRAFT_READABILITY` block: draft paper now uses `--surface-strong` (opaque), drops the gradient overlay, adds `backdrop-filter: blur(6px)` and per-theme high-contrast text colors (`#f5f7f1` dark-lime, `#0e1a2e` wave-blue, `#0c1410` light-lime). Added `PMD:V2:STEP28_TEMPLATE_HELP` styles for `.v2-template-help` (helper card under the template select) and the `.v2-onboarding` 3-step block (responsive grid that collapses on mobile).
- `src/delivery_reports/web/templates/dashboard_v2.html` — added the onboarding `<section id="v2-onboarding">` with title "Как собрать отчёт за 3 шага", three numbered steps, and a "Скрыть подсказку" button wired to localStorage key `pmd:onboarding-hidden:v1` via inline IIFE (no backend). Added `.v2-template-help` block under the template select with one-line explanations for each of the 4 templates. Renamed AI rail button **"Executive style" → "Для руководителя"**; tooltips updated to the requested copy ("Уберёт лишние детали, оставит главное.", "Сделает акцент на рисках, решениях и следующих шагах.", "Найдёт риски и блокеры в черновике."). Inbox empty-state copy clarified: "Сначала создайте проект в Super Admin или добавьте проект в форме заметки."
- `src/delivery_reports/config.py` — `app_version` v2.24.1 → v2.24.2 (patch: UX/copy polish, no schema or routes touched).
- `tests/test_web_app.py` — 2 new tests: dashboard renders the onboarding block + template help with all 4 template names; AI rail uses the Russian "Для руководителя" label and the new tooltip copy (English "Executive style" gone).

**Reason:** Reduce time-to-first-report for new users; make the dark/wave themes usable; explain template behavior in-context.

**What to manually verify:**
- Switch theme to **wave-blue** and **dark-lime** — draft paper text must be high-contrast, not faded.
- Click **"Скрыть подсказку"** on the onboarding block — it disappears and stays hidden after reload (clear `localStorage` key `pmd:onboarding-hidden:v1` to bring it back).
- In the draft header, confirm the helper card lists all four templates with explanations.
- AI rail shows **"Для руководителя"** instead of "Executive style" in both the live (with draft) and disabled (empty) states.
- Open an inbox card with no candidates: copy reads "Сначала создайте проект в Super Admin или добавьте проект в форме заметки."

**Rollback notes:** All changes are template/CSS/copy + a single config line. No routes, payments, DB, or auth touched. Revert by undoing the template + CSS additions and bumping `app_version` back to v2.24.1.

---

## 2026-04-28 — v2.24.3: HOTFIX inbox bind dropdown is invisible (Step 28A)

**Bug:** In v2.24.2 Mini App the inbox section "Заметки без проекта" still rendered the fallback message "Сначала создайте проект в Super Admin или добавьте проект в форме заметки." even though projects (Delivery Reports, Bank Dashboard, Внедрение категорийного кэшбэка (BONUS-2055), ТЕСТ) already existed in SQLite. Root cause: `_build_dashboard_context` filters projects by `user.telegram_user_id`; in production the projects existed under a different `owner_user_id` (legacy data / seeder run with another id), so the user-scoped list was empty and the template's `{% if projects %}` branch fell through.

**Files changed:**
- `src/delivery_reports/web_app.py` — added a dedicated `inbox_projects` list to the dashboard context (both authed and auth-required branches). It starts as the user-scoped `projects` list and falls back to all non-pseudo projects in DB when the user-scoped list is empty (deduplicated by case-insensitive name, "Без проекта" filtered out). `/inbox/{id}/resolve` already calls `resolve_or_create_project`, which reconciles ownership when binding, so this is safe.
- `src/delivery_reports/web/templates/dashboard_v2.html` — both inbox-card form branches (visible cards + collapsed `<details>` overflow) switched from `projects` → `inbox_projects` for the `{% if … %}` guard and the `{% for project in … %}` loop.
- `src/delivery_reports/config.py` — `app_version` v2.24.2 → v2.24.3 (patch: bug fix only).
- `tests/test_web_app.py` — 1 new regression test: with all four real projects under a different `owner_user_id` (999_001) and a fresh authenticated user (777_777) with no projects, the V2 dashboard still renders `<select name="project_name">` with options for "Delivery Reports", "Bank Dashboard", "Внедрение категорийного кэшбэка (BONUS-2055)", and "ТЕСТ"; the "Без проекта" pseudo-project is excluded; and the fallback message is gone.

**Verification:** `python -m compileall src/delivery_reports` ✓ · `pytest -q` 120 passed.

**What to manually verify in production:**
- Open the Mini App → "Заметки без проекта" → every card shows the "Выберите проект — заметка попадёт в нужный блок отчёта." form with a populated `<select>`.
- Pick "Delivery Reports", press "Привязать" — note moves into the Delivery Reports section of the next draft.
- "Без проекта" never appears in the dropdown options.

**Rollback notes:** Single-purpose hotfix. Revert by removing the `inbox_projects` block in `_build_dashboard_context`, switching the template back to `projects`, and bumping `app_version` to v2.24.2.

---

## 2026-04-28 — v2.24.4: Friendly /inbox copy in Telegram bot (Step 28C)

**Problem:** Bot `/inbox` ended its list with a technical hint ("Resolve: `разобрать 15 DC701` или `/inbox resolve 15 DC701`") that confused non-technical PMs. The Mini App already has a one-click bind form; the bot should point users there instead.

**Files changed:**
- `src/delivery_reports/bot_app.py` — `cmd_inbox` final hint replaced with: 📲 "Проще: откройте Mini App → блок «Заметки без проекта» → выберите проект → Привязать.", followed by an italic "Для ручной команды:" line that preserves the working `/inbox resolve 15 DC701` example. After the main message, an inline `WebAppInfo` Mini App button ("📥 Разобрать в Mini App") is sent so users can open the dashboard with one tap. Skipped silently when `public_web_app_url` is empty (e.g., local dev / non-HTTPS), keeping the command working in every environment. The `/inbox resolve <note_id> <code>` command path is **untouched**.
- `src/delivery_reports/config.py` — `app_version` v2.24.3 → v2.24.4 (patch: copy + UX hint, no schema/routes/auth touched).
- `tests/test_bot_inbox.py` — new file with 3 focused tests: friendly copy + advanced-fallback labeling, Mini App inline button is appended with a `web_app=…` URL pointing at `public_web_app_url`, and the button is skipped when `public_web_app_url` is empty.

**Verification:** `python -m compileall src/delivery_reports` ✓ · `pytest -q` 123 passed.

**What to manually verify:**
- Send `/inbox` in the bot — list ends with the new 📲 line and an italic "Для ручной команды:" example, and a follow-up message offers a "📥 Разобрать в Mini App" button.
- Tapping the Mini App button opens the dashboard.
- `/inbox resolve <id> <project>` still binds the note to the project.

**Rollback notes:** Restore the previous single hint line in `cmd_inbox` and remove the follow-up Mini App message; bump `app_version` back to v2.24.3.

---

## 2026-04-28 — v2.24.5: Canvas animation visible on Windows (Step 29)

**Problem:** On Windows the constellation background was invisible or very faint, especially in light/wave themes. Root causes: `inset: 0` unsupported in Edge Legacy; `--c-dot/--c-line/--c-ambient` opacities too low for Windows gamma; `window.matchMedia` call unguarded; `getContext('2d')` unguarded; CSS custom property reads could return empty string.

**Files changed:**
- `src/delivery_reports/web/static/v2/themes.css` — bumped `light-lime` canvas colors: dot `0.28→0.52`, line `0.10→0.20`, ambient `0.16→0.30`. Bumped `wave-blue`: dot `0.30→0.52`, line `0.10→0.22`, ambient `0.16→0.28`.
- `src/delivery_reports/web/static/v2/dashboard_v2.css` and `landing_v2.css` — added explicit `top:0; right:0; bottom:0; left:0` before `inset: 0` as fallback for browsers that don't support `inset`.
- `src/delivery_reports/web/static/v2/v2_ui.js` — Step 29 hardening:
  - `REDUCE` initialization wrapped in `try/catch`.
  - `cssv()` wrapped in `try/catch`.
  - Added `THEME_FALLBACKS` map — when CSS custom props return '' (older Chromium), `updateCanvasColors()` fills `cDot/cLine/cAmb` from hardcoded values that match the updated `themes.css` values.
  - `buildDots()`: dot density increased for light themes (`9000/11000` vs `12000/18000`), alpha raised (`0.42–0.84` light-lime, `0.32–0.70` wave-blue, was `0.26–0.62` / `0.14–0.36`).
  - `drawFrame()`: `lineAlphaMult` raised for light themes (`0.32` light-lime, `0.24` wave-blue, was `0.22`/`0.14`); grid opacity raised `0.092→0.11`; dot shadow radius bumped (`10/7` vs `8/5`).
  - `resizeCanvas()` and `drawFrame()` guard early-exit when `!canvas || !ctx || !W || !H`.
  - `initCanvas()`: `getContext('2d')` wrapped in `try/catch` and null-guarded.
  - `REDUCE=true` path: dot movement skipped (static frame), ensuring a visible non-animated state with dots+grid on Windows accessibility settings.
- `src/delivery_reports/config.py` — `app_version` v2.24.4 → v2.24.5 (patch: JS/CSS visual fix, no backend changes).

**Verification:** `python -m compileall src/delivery_reports` ✓ · `pytest -q` 123 passed.

**What to manually verify:**
- Windows Chrome/Edge: open landing page and dashboard in **light-lime** and **wave-blue** themes — dots and subtle proximity lines should be clearly visible but not overpowering.
- Windows with "Reduce motion" enabled: static dots + light-lime grid visible (no animation).
- macOS/mobile: dark-lime unchanged visually; light themes slightly brighter dots.

**Rollback notes:** Static files only + `app_version`. Revert by restoring previous `themes.css` opacity values and the previous `v2_ui.js`; bump `app_version` back to v2.24.4.

---

## 2026-04-29 — Step 34: Local SQLite backup/restore scripts (dev tooling)

**Task:** Simple backup/restore for MVP testing when SQLite on Render Free / local can be wiped on deploy.

**Files changed:**
- `scripts/backup_db.py` — loads `load_settings()`, resolves `DB_PATH` (relative paths from repo root). If DB exists: `shutil.copy2` to `backups/delivery_reports_YYYYMMDD_HHMMSS.db` and `backups/delivery_reports_latest.db`. Optional `DELIVERY_REPORTS_BACKUP_DIR` overrides backup folder. Exit `0`; if DB missing, prints skip message and exits `0`.
- `scripts/restore_db.py` — copies `delivery_reports_latest.db` to configured `DB_PATH`, creates parent dirs. Exit `1` if backup missing.
- `.gitignore` — `data/*.db`, `data/*.db-*`, `backups/` (existing `data/` retained).
- `tests/test_backup_restore_scripts.py` — subprocess tests: backup creates latest + timestamped; restore creates parent path; missing backup exits 1.

**Product `APP_VERSION`:** unchanged (tooling only).

**Tests:** 154 passed, `compileall` on `src/delivery_reports` + `scripts` clean.

---

## 2026-04-28 — v2.25.0: Text-first / FREE–PRO copy positioning (Step 30A)

**Task:** Landing and bot copy over-emphasized voice as a default FREE feature, creating wrong expectations. Repositioned to: FREE = text notes + project recognition + draft report; PRO = voice + AI editor; TEAM = shared projects + team workflow.

**Files changed:**
- `src/delivery_reports/web/templates/landing_v2.html`:
  - `<meta description>` — updated to "FREE: текстовые заметки. PRO: voice и AI-редактор."
  - **Hero**: h1 → "Ежедневные PM-отчёты без вечернего хаоса"; sub → "Пишите апдейты в течение дня — PM Digest сам разложит их по проектам…"; added `<p>FREE: текстовые заметки. PRO: voice и AI-редактор.</p>`.
  - **Phone mockup chat**: bot greeting → "Пришлите апдейт текстом — я разложу его по проектам"; voice waveform mock replaced with a text user message.
  - **Testimonial**: "диктую голосовые заметки" → "добавляю короткие апдейты в течение дня — вечером получаю готовый черновик."
  - **Step 01**: icon 🎙️ → ✏️; title "Пишите или диктуете заметки" → "Пишите апдейты текстом"; desc — notes Voice is PRO.
  - **Features section** sub: removed "Голос" from the opener; added "Voice — в PRO."
  - **Feature card "Voice → text"** — was FREE → is now **PRO** card with title "Voice → текст". New FREE card "Текст → отчёт" (✏️) introduced in its place.
  - **New section "Почему не просто ChatGPT/Gemini?"** inserted before Security section explaining persistent context (projects, aliases, templates, history).
  - **Demo modal** initial step title "Заметка или голос" → "Апдейт текстом"; desc notes Voice is PRO.
- `src/delivery_reports/web/static/v2/v2_ui.js` — `DEMO_STEPS[0]`: ico ✏️, title "Апдейт текстом", desc includes "Voice — в PRO." `DEMO_STEPS[1]`: title "Разложит по проектам" (was "Парсинг и структура").
- `src/delivery_reports/bot_app.py` — `/start` message rewritten: concise text-first welcome ("Пишите апдейты текстом…"), explicit "🎙 Голосовые заметки и AI-редактор доступны в PRO." line. Removed redundant `_maybe_send_mini_app_entry` follow-up call (the inline Mini App button already covers it).
- `src/delivery_reports/web/templates/dashboard_v2.html` — onboarding step 1: "текстом здесь или voice в Telegram" → "текстом здесь или в Telegram. Voice доступен в PRO."; empty-state copy updated to remove voice-as-default; voice callout title/desc updated to label voice as PRO.
- `src/delivery_reports/config.py` — `app_version` v2.24.5 → v2.25.0 (minor: user-visible copy/positioning change).
- `tests/test_copy_positioning.py` — **new** file with 8 tests covering: landing no longer contains "заметку или голосовое"; landing contains "FREE: текстовые заметки" and PRO; hero sub is text-first; Voice card tagged PRO not FREE; step 01 updated; testimonial updated; ChatGPT section present; /start is text-first with PRO voice note.

**Verification:** `python -m compileall src/delivery_reports` ✓ · `pytest -q` 131 passed.

**Rollback notes:** Template + JS + config copy changes only. No routes, DB, auth, or payments touched. Revert by restoring the previous landing/dashboard HTML, `v2_ui.js` DEMO_STEPS, bot_app `/start` text, and bumping `app_version` back to v2.24.5.

---

## 2026-04-28 — v2.25.1: Landing sales polish (Step 30B)

**Task:** Improve landing page sales quality after text-first repositioning.

**Files changed:**
- `src/delivery_reports/web/templates/landing_v2.html`
  - Hero h1 changed to "Ваш личный ассистент для ежедневных отчётов"; subcopy uses "короткие апдейты".
  - ChatGPT/Gemini section reframed positively: "Можно — и ChatGPT справится…" + "PM Digest уже настроен"; title changed from argumentative to "А можно просто ChatGPT / Gemini?".
  - Feature grid: added two new FREE cards ("Шаблоны отчётов", "История и финалы") to eliminate lonely last-row card; Team dashboard copy tightened.
  - "How it works" section replaced with a visual `s1-flow-grid` containing four flow steps with inline HTML mockups (chat bubble, intent chips, mini report paper, send buttons).
- `src/delivery_reports/web/static/v2/landing_v2.css`
  - Added `PMD:V2:LANDING_FLOW` block: `s1-flow-grid` (4-col → 2-col → 1-col responsive), `s1-flow-step`, `s1-flow-mock`, `s1-flow-chat-bubble`, `s1-flow-chips`, chip colour variants per theme, `s1-flow-paper`, `s1-flow-send`, `s1-flow-arrow`.
- `src/delivery_reports/config.py` — `app_version` v2.25.0 → v2.25.1.
- `tests/test_copy_positioning.py` — 3 new assertions: hero "Ваш личный ассистент", ChatGPT section soft framing ("уже настроен", no "Почему не просто"), no "парсинг", flow grid rendered.

**Tests:** 134 passed (0 failures), `compileall` clean.

---

## 2026-04-28 — v2.25.2: Project setup + report-date clarity (Step 31)

**Task:** Make project creation, inbox routing and the report-date model obvious without slash commands.

**Files changed:**
- `src/delivery_reports/web_app.py`
  - New `POST /projects` route. Reuses `resolve_or_create_project` (no DB schema change), then merges optional comma-separated aliases via `repository.upsert_project`. Redirects back to dashboard with notice.
  - `_build_dashboard_context` now exposes `today_iso` and `report_date_label`.
- `src/delivery_reports/web/templates/dashboard_v2.html`
  - Page header gets a prominent "📅 Отчёт за: <date> · сегодня" label.
  - Draft-meta date item now reads "📅 Отчёт за: <date>".
  - Empty/no-project state: full-width "🚀 Начните с проекта" card with `project_name` + `aliases` form posting to `/projects`.
  - With existing projects: collapsed `<details>` "+ Новый проект" anchor (`#v2-project-setup`) so the inbox can link in.
  - Every inbox-bind row now includes "+ Новый проект" link to `#v2-project-setup`.
  - Replaced "Сначала создайте проект в Super Admin..." with "Добавьте проект здесь или выберите существующий — после этого заметка попадёт в отчёт.".
- `src/delivery_reports/web/static/v2/dashboard_v2.css`
  - New `PMD:V2:STEP31_PROJECT_SETUP` block: `.v2-report-date-label`, `.v2-project-setup` (empty + collapsed variants), inputs/textarea styles, `.v2-inbox-new-project` button, mobile stacking.
- `src/delivery_reports/config.py` — `app_version` v2.25.1 → v2.25.2.
- `tests/test_web_app.py` — 6 new tests:
  - `test_v2_dashboard_shows_project_setup_card_when_no_projects`
  - `test_v2_dashboard_collapsed_setup_when_projects_exist`
  - `test_v2_dashboard_renders_report_date_label`
  - `test_v2_inbox_card_includes_new_project_link`
  - `test_post_projects_creates_project_with_aliases`
  - `test_post_projects_rejects_blank_name`

**Tests:** 140 passed (was 134), `compileall` clean.

---

## 2026-04-28 — v2.25.3: Bulk inbox bind (Step 32)

**Task:** Let users bind multiple inbox notes to a project in one action instead of one-by-one.

**Files changed:**
- `src/delivery_reports/web_app.py`
  - New `POST /inbox/bulk-resolve` route. Reads raw body with `parse_qs` to collect all repeated `note_ids` fields. Validates ownership per note. Calls existing `resolve_or_create_project` + `repository.update_note_project`. Skips notes not owned by the authenticated user. Returns "Привязано N заметок к проекту X." notice.
- `src/delivery_reports/web/templates/dashboard_v2.html`
  - Inbox section wrapped in `<form id="v2-bulk-inbox-form" action="/inbox/bulk-resolve">`.
  - Sticky `v2-bulk-bar` at top: "Выбрать видимые" master checkbox, project `<select>`, "Привязать выбранные" submit.
  - Each inbox card (visible + collapsed rest) gets `<input type="checkbox" name="note_ids" value="{{ card.note.id }}">`.
  - Candidate quick-bind buttons converted to `type="button"` with `data-note-id`/`data-project` — JS selects checkbox + sets bulk select then submits bulk form.
  - Individual per-card `v2-inbox-bind` forms retained for one-at-a-time use.
  - Overflow note copy updated: "Можно выбрать видимые заметки и привязать их к проекту. Остальные доступны в раскрытом списке."
  - Inline `<script>` for: master-checkbox select-all, indeterminate sync, quick-bind click handler.
- `src/delivery_reports/web/static/v2/dashboard_v2.css`
  - New `PMD:V2:STEP32_BULK_INBOX` block: `.v2-bulk-bar`, `.v2-bulk-bar-selectall`, `.v2-bulk-checkbox`, `.v2-bulk-select`, `.v2-bulk-bind-btn`, `.v2-bulk-cb-label`. Mobile stacking at 600px.
- `src/delivery_reports/config.py` — `app_version` v2.25.2 → v2.25.3.
- `tests/test_web_app.py` — 4 new tests:
  - `test_v2_inbox_renders_bulk_form_and_checkboxes`
  - `test_bulk_resolve_binds_multiple_notes` (comma-separated ids)
  - `test_bulk_resolve_repeated_fields` (one checkbox per repeated POST field)
  - `test_bulk_resolve_does_not_bind_other_user_notes`

**Tests:** 144 passed (was 140), `compileall` clean.

---

## 2026-04-28 — v2.25.4: Bulk inbox HTML5 validation hotfix (Step 32B)

**Task:** Fix native browser validation blocking bulk submit ("Выберите один из пунктов списка") caused by invalid nested forms: per-card `v2-inbox-bind` forms lived inside the bulk form, so the browser treated empty `required` per-card selects as part of the bulk submit.

**Files changed:**
- `src/delivery_reports/web/templates/dashboard_v2.html`
  - Bulk form (`id="v2-bulk-inbox-form"`) now contains only the toolbar (project select + submit + master checkbox).
  - Inbox card checkboxes use `form="v2-bulk-inbox-form"` so they still POST with bulk-resolve.
  - Per-card `action="/inbox/{id}/resolve"` forms are siblings (never nested inside the bulk form).
- `src/delivery_reports/web/static/v2/dashboard_v2.css`
  - `.v2-bulk-inbox-form`: `display: contents` → `display: block; margin-bottom: 10px;` (form is a real wrapper again).
- `src/delivery_reports/config.py` — `app_version` v2.25.3 → v2.25.4.
- `tests/test_web_app.py` — `test_v2_bulk_form_not_nested_per_card_required_selects` (regex slice of bulk form: exactly one `required`, no `class="v2-inbox-bind"`, checkboxes have `form="v2-bulk-inbox-form"`).

**Tests:** 145 passed (was 144), `compileall` clean.

---

## 2026-04-28 — v2.25.5: False risk classification + cross-section dedup (Step 33)

**Task:** Stop routing explanatory “проблема…” text into risks; tighten long-update decision vs risk; dedupe identical bullets across draft sections for one project.

**Root cause:** `_split_by_intent` sent any line containing substring `«проблем»` to `risk_lines`, including atomic lines prefixed with `Что сделано: … статус по проблеме …`, so the same content could appear under both done and risks after prefix stripping.

**Files changed:**
- `src/delivery_reports/services/parsing.py` — `_split_by_intent`: after metadata skip, honor explicit prefixes first (`что сделано:`, `план:`, `риск:`, `блокер:`). Removed naive `«проблем»` token from the risk heuristic (keep `риск` / `блокер` / `завис` / `пауз`).
- `src/delivery_reports/services/long_update_split.py` — expanded `_STRONG_DECISION_PATTERNS` (`не будем`, `решили не`, `чтобы не сломать`, `можем сломать`); expanded `_STRONG_RISK_PATTERNS` (`есть риск`, `может задержаться`, `можем не успеть`); done verbs: `закрыли`, `проверили`, `выяснили`.
- `src/delivery_reports/services/draft_builder.py` — `_cross_section_norm_key`, `_dedupe_sections_in_priority_order` (blocker > risk > decision > done > plan > question) applied in `_render_project_block` after limit/compact/clean. Added `import re`.
- `src/delivery_reports/config.py` — `app_version` v2.25.4 → v2.25.5.
- `tests/test_step33_intent_dedup.py` — 6 tests (classification + MyID-style draft + cross-section dedup).

**Tests:** 151 passed (was 145), `compileall` clean.

---

## 2026-04-29 — v2.25.6: Real-world report regression tests (Step 35)

**Task:** Automate regression coverage for the parse → split → daily draft pipeline using representative «template»-style examples (no full megafixture), plus optional CLI smoke over the same file.

**Files changed:**
- `tests/fixtures/report_examples.txt` — **new**; 11 `---BEGIN key---` … `---END---` blocks (Visa «Риск: нет», PAMS «Риски: Отсутствуют», О!Афиша backend risk, BONUS-2055/MCC multi-project, Тен Арина «Проблема:» + «Блокер:» / выявлен блокер, Caller ID risks, DC701 migration blockers, MRZ без рисков, Мээрим-style multi-project + Jira, chat noise/FYI/YouTube).
- `tests/test_real_report_examples.py` — **new**; 9 tests: no crash; no `⚠️ Риски` when risk explicitly absent/none; explicit risk phrases preserved; «Проблема:» not auto-risk; blockers + Android design line; multi-project section separation; Jira keys preserved in output; cross-section bullet dedup; standard vs concise vs `risk_focus` differ with risks before done in `risk_focus`.
- `scripts/run_report_regression.py` — **new**; stdlib-only: reads fixture, prints example count, summed section headers, risk/blocker presence, warnings (`needs_review`, empty draft).
- `src/delivery_reports/services/draft_builder.py` — `_route_done_lines` / `_route_risk_lines`: route lines matching **«Блокер:»** / **«Выявлен блокер»** from done text into `aggregate.blocker_items` so structured daily reports do not mis-file blockers as plain done items.
- `src/delivery_reports/config.py` — `app_version` v2.25.5 → v2.25.6 (patch: draft routing behaviour).

**Reason:** Catch report-quality regressions without manual runs across every scenario; small draft fix aligns output with expected blocker sections on real messages.

**Tests:** `python -m compileall src/delivery_reports scripts` clean; `pytest -q` **163 passed** (includes 9 in `test_real_report_examples.py`).

**Rollback notes:** Revert fixture/tests/script if needed; revert `draft_builder` blocker routing and set `app_version` back to v2.25.5 if the routing change is undesirable.

---

## 2026-04-29 — v2.25.7: Strip assistant markdown/meta from report input (Step 36)

**Task:** Remove ChatGPT-style intros, blockquote/list markdown (`>`, `*`, `**`) and simple “Имя, привет.” greetings before parsing so drafts keep only real PM content; stop treating neutral «риски оценены» as a fuzzy risk trigger; bias future «запросим / заводим» clauses toward plan in long-update classification.

**Files changed:**
- `src/delivery_reports/services/report_text_cleaner.py` — **new** `pre_clean_incoming_report_text()` (assistant/meta substring drop, repeated `>` + list-marker peel, bold removal, greeting prefix).
- `src/delivery_reports/services/parsing.py` — run pre-clean at start of `parse_note_blocks` and `parse_note_text`; replace naive «риск» substring heuristic with `_line_heuristic_suggests_risk()` (word-boundary + exception for `риски? оценен…`).
- `src/delivery_reports/services/long_update_split.py` — `_STRONG_PLAN_PATTERNS`: `запросим`, `заведём`/`заведем`, `заводим`.
- `tests/fixtures/report_examples.txt` — **new** `assistant_myid_markdown` block.
- `tests/test_real_report_examples.py` — MyID project + `test_assistant_markdown_meta_stripped`; project list extended.
- `scripts/run_report_regression.py` — mirror MyID in `_projects()`.
- `scripts/__init__.py` — **new** so `python -m scripts.run_report_regression` works from repo root.
- `src/delivery_reports/config.py` — `app_version` v2.25.6 → v2.25.7.

**Tests:** `python -m compileall src/delivery_reports scripts` · `pytest -q` · `python -m scripts.run_report_regression`.

**Rollback notes:** Remove `pre_clean_incoming_report_text` calls and restore previous risk heuristic; set `app_version` back to v2.25.6.

---

## 2026-04-29 — v2.25.8: Landing V2 UI polish (hero mockup, FAQ accordion, footer)

**Task:** CSS/HTML-only polish for `landing_v2.html`: hero plan badges, enhanced phone mockup shell, section spacing, theme labels + tooltips, FREE CTA styling, security stroke icons, multi-column footer, FAQ as `details`/`summary` accordion, card hover glow + fade-in.

**Files changed:**
- `src/delivery_reports/web/templates/landing_v2.html` — structure updates (badges, FAQ, footer columns, nav FAQ link, SVG security icons, theme control markup).
- `src/delivery_reports/web/static/v2/landing_v2.css` — animations, spacing, phone pseudo-layers, accordion, footer grid, plan/tooltip/card styles; tablet hero keeps mockup until 900px.
- `src/delivery_reports/config.py` — `app_version` v2.25.7 → v2.25.8.

**Rollback notes:** Revert the two files above and `app_version` to v2.25.7.

---

## 2026-04-29 — v2.25.9: Landing V2 aidentika-style light redesign (Step 38)

**Task:** Redesign the PM Digest V2 landing page as a clean white aidentika-style page with huge centered italic typography, lime CTAs, dark pricing/footer blocks, and no canvas/neon/particle background.

**Files changed:**
- `src/delivery_reports/web/templates/landing_v2.html` — rebuilt the landing markup around the requested centered hero, marquee, feature cards, comparison section, how-it-works flow, dark pricing, FAQ/security, and footer columns; removed theme switcher, canvas, demo modal, and external landing JS dependency.
- `src/delivery_reports/web/static/v2/landing_v2.css` — replaced the dark/glow V2 landing styles with a full light theme, aidentika-style typography, lime CTA/badge treatments, responsive one-column mobile layout, dark pricing/footer, and 20s marquee animation.
- `src/delivery_reports/config.py` — `app_version` v2.25.8 → v2.25.9.

Tests: python -m compileall src/delivery_reports scripts clean; pytest -q 164 passed.

**Reason:** Align the public landing page with the requested clean white visual direction while keeping PM Digest’s real Telegram bot + Mini App positioning.

**Rollback notes:** Revert `landing_v2.html`, `landing_v2.css`, and set `app_version` back to v2.25.8.

---


---

## 2026-04-29 — v2.25.10: Hybrid neon landing restoration (Step 38C)

**Task:** Keep the Step 38 content improvements while restoring the previous committed landing visual identity: animated canvas background, theme switcher, neon/glass cards, glowing CTAs, and hero phone mockup.

**Files changed:**
- `src/delivery_reports/web/templates/landing_v2.html` — restored the committed V2 landing shell (theme bootstrap, canvas layer, theme buttons, hero phone mockup, demo modal, V2 UI script) and inserted the Step 38 comparison section in the old section layout; kept text-first FREE/PRO positioning and clearer CTA copy.
- `src/delivery_reports/web/static/v2/landing_v2.css` — restored the committed neon/glass landing styles and added `PMD:V2:LANDING_COMPARE` styles for the comparison cards using theme tokens, glow, blur, and responsive stacking.
- `src/delivery_reports/config.py` — `app_version` v2.25.9 → v2.25.10.

**Reason:** The plain white Step 38 landing lost too much of PM Digest’s Telegram/Mini App visual identity. This hybrid keeps the better content while returning to the richer V2 look.

**Rollback notes:** Revert `landing_v2.html`, `landing_v2.css`, and set `app_version` back to v2.25.9.

## 2026-04-28 — v2.23.2: Prevent failed voice transcription from polluting reports (Step 26)

**Task:** Failed voice transcriptions were saved as technical garbage notes (`voice-note: transcription failed; file_id=...`), polluting the dashboard, inbox, and generated drafts. This step silences that path entirely.

**Files changed:**
- `src/delivery_reports/services/transcription.py` — introduced `TranscriptionResult(text, ok, reason)` frozen dataclass; `transcribe()` now returns this object instead of a raw `str`; added structured `reason` values: `"ok"`, `"disabled"`, `"no_whisper"`, `"whisper_error"`, `"empty_result"`; all failure branches log internally at appropriate levels (warning/error/info) without exposing file IDs or tokens.
- `src/delivery_reports/bot_app.py` — `on_voice_message` updated to consume `TranscriptionResult`; on `ok=False` it sends a human-readable message and **returns without storing any note**, preventing technical text from entering the DB; `disabled` reason gets its own copy; added `import logging` and module-level `_log` logger; removed `TranscriptionResult` import guard.
- `src/delivery_reports/config.py` — bumped `app_version` to `"v2.23.2"` (both dataclass default and `load_settings` fallback).
- `tests/test_transcription.py` — new file; 9 tests covering disabled/mock/no_whisper/whisper_error/empty_result/success modes, return-type regression guard, and a helper asserting technical strings never appear in `.text`.

**Reason:** Technical fallback text (`voice-note: transcription failed; file_id=...`) was leaking into PM reports, making drafts unreadable. The root cause was treating failed transcription the same as successful text input.

**Rollback notes:** Revert `transcription.py` to return `str` and restore the old `on_voice_message` body. The DB schema is unchanged; no migration needed.

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
