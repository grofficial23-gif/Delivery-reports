# V2 Rollback and Feature Flag Plan

## Goal
Safely prepare the project for V2 UI rollout while preserving current V1 behavior as the default and rollback point.

## Feature Flag
- Env var: `DASHBOARD_UI_VERSION`
- Supported values: `v1`, `v2`
- Default: `v1`

Current routing behavior in `GET /dashboard`:
- if `DASHBOARD_UI_VERSION == "v2"` -> render `dashboard_v2.html`
- otherwise -> render `index.html` (current V1 dashboard)

## V1 Files (Rollback Baseline)
- `src/delivery_reports/web/templates/index.html`
- `src/delivery_reports/web/static/app.css`
- `src/delivery_reports/web/static/app.js`

These files must remain intact and continue to support production MVP behavior.

## V2 Files (Isolated UI Layer)
- `src/delivery_reports/web/templates/dashboard_v2.html`
- Future V2 static files (recommended):
  - `src/delivery_reports/web/static/v2/dashboard_v2.css`
  - `src/delivery_reports/web/static/v2/dashboard_v2.js`
  - `src/delivery_reports/web/static/v2/dna_spiral.js`

## How to Enable V2
Set env before app start:

```bash
export DASHBOARD_UI_VERSION=v2
```

Then restart the app process.

## Fast Rollback to V1
Set env back to:

```bash
export DASHBOARD_UI_VERSION=v1
```

Restart the app process.  
This instantly restores the existing V1 template path for `/dashboard`.

## Routes That Must Not Break
Do not change behavior/contract of existing POST routes:
- `POST /notes`
- `POST /tasks`
- `POST /tasks/{task_id}/status`
- `POST /draft/build`
- `POST /draft/finalize`
- `POST /draft/send`
- `POST /final/send`
- `POST /inbox/{note_id}/resolve`
- `POST /template`
- `POST /onboarding/complete`
- `POST /auth/telegram`
- `POST /admin/users/{target_user_id}/plan`

Also keep:
- `GET /dashboard`
- `GET /admin`
- `GET /`

## Behavior Parity Requirements (V1 vs V2)
Regardless of UI template, these actions must work identically:
- add note
- build draft
- draft preview visibility
- send draft to Telegram
- finalize report
- send final report to Telegram
- tasks add/status updates
- inbox resolve
- template selection
- onboarding completion
- auth flow in Telegram Mini App

## Safety Notes
- V1 remains default and rollback point.
- V2 should evolve in isolated files.
- Avoid mixing V2 styles/scripts into V1 assets.
