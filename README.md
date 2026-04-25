# Delivery Reports Bot (MVP)

Local-first Telegram bot for daily PM report drafting with GRACE-lite module contracts and RAG-ready storage structure.

## What works now
- Accepts text notes in Telegram.
- Accepts voice notes and transcribes locally with Whisper (if installed).
- Stores notes in SQLite.
- Auto-detects project by aliases, extracts Jira links, and splits done/plan/risk.
- Uses a hybrid clarification flow: tries to detect project automatically, then asks short follow-up questions if confidence is low.
- Remembers Telegram `full_name` as the default author/manager and supports per-user defaults.
- Splits one long message into multiple blocks by `Эпик:` or `Проект:` headings.
- Supports an epic registry and tries to map `эпик -> проект` automatically.
- Builds one daily draft (`/draft` or button `Собрать отчет`).
- Supports draft review modes: `Показать черновик` and `Исправить черновик` (`короче`, `акцент на риск`, `обычный`).
- Supports final report fixation (`Зафиксировать финальный`) with DB history.
- Keeps a template registry (`standard`, `concise`, `risk_focus`, `team`) and per-user template selection.
- Has a retry flow for unresolved notes (`/reprocess`) and preserves notes when voice transcription fails.
- Adds PM routine commands: personal tasks (`/task`, `/mytasks`) and unresolved inbox (`/inbox`).
- Keeps the keyboard minimal and supports smart phrases like `статус`, `мои задачи`, `inbox`, `черновик`, `финальный`, `задача: ...`, `готово 12`.
- Preserves explicit note sections like `Статус:`, `Что сделано:`, `План на завтра:`, `Риски:` when the user writes in a structured PM format.
- Includes a Telegram Mini App with automatic Telegram-profile auth, per-user project isolation, onboarding, and a mobile/desktop-friendly workspace.
- Sends daily draft at 17:30 local timezone on weekdays.

## Quick start
1. Create venv and install:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
```
2. Configure env:
```bash
cp .env.example .env
```
3. Set required keys in `.env`:
- `TELEGRAM_BOT_TOKEN`
- `DEFAULT_MANAGER_NAME`
- `DEFAULT_LEAD_NAME`

Optional:
- `OWNER_USER_ID` (if set, scheduled drafts can be sent before `/start`)
- `TRANSCRIBE_MODE=local_whisper|mock|disabled`
- `WHISPER_MODEL=base`
- `PUBLIC_WEB_APP_URL=https://your-public-mini-app.example.com`
- `WEB_SESSION_SECRET=some-random-secret`

Current safe default for quick launch:
- use `TRANSCRIBE_MODE=disabled` if you want the bot running now without installing Whisper.

4. Run:
```bash
python -m delivery_reports.main
```

Shortcut:
```bash
./run_local.sh
```

Local web dev:
```bash
./run_web.sh
```

By default the local panel runs on [http://127.0.0.1:8787](http://127.0.0.1:8787).
For real Telegram Mini App usage, Telegram Bot API expects an HTTPS Web App URL. According to the official Bot API, `WebAppInfo.url` must be an HTTPS URL, while the Mini App docs describe validating `Telegram.WebApp.initData` on the backend and using `setChatMenuButton` / Mini App buttons to launch it. Sources:
- [Telegram Bot API: WebAppInfo](https://core.telegram.org/bots/api)
- [Telegram Mini Apps](https://core.telegram.org/bots/webapps)

## Bot usage
- Team-facing usage guide: [docs/TEAM_GUIDE_RU.md](/Users/grafk1n/Documents/Delivery%20Reports%20/docs/TEAM_GUIDE_RU.md)
- Product strategy v2: [docs/PRODUCT_STRATEGY_V2_RU.md](/Users/grafk1n/Documents/Delivery%20Reports%20/docs/PRODUCT_STRATEGY_V2_RU.md)
- `/start` start bot and bind owner chat.
- `/app` send a launch button for the personal Mini App and configure the Telegram menu button when `PUBLIC_WEB_APP_URL` is set.
- `/pro` show pricing and Premium plan preview.
- `/add <text>` add note manually.
- `/status` show a short daily control summary.
- `/draft` build draft now.
- `/showdraft` show the latest draft for today.
- `/fixdraft <короче|акцент на риск|обычный>` rebuild the current draft style.
- `/finalize` save the latest draft as final report.
- `/final` show the latest final report for today.
- `/reprocess` retry parsing unresolved notes for today.
- `/task add <text>` add PM task.
- `/task done|wait|progress|open <id>` update task status.
- `/mytasks` show active personal tasks.
- `/inbox` show unresolved notes.
- `/inbox resolve <note_id> <project>` resolve one inbox note manually.
- Smart text shortcuts also work without slash commands.
- Current reply keyboard is optimized around `📋 Собрать отчёт`, `📊 Статус`, `✅ Мои задачи`, `⭐ PRO`.
- `/templates` list available report templates.
- `/template <standard|concise|risk_focus|team>` set your default template.
- `/projects` list project directory.
- `/epics` list epic registry.
- Send plain text: stored as note.
- Send voice: transcribed and stored as note when transcription is enabled.
- If the bot is unsure about the project, answer with the project name or configure it directly:
  - `проект: Онбординг | алиасы: onboarding, идентификация | руководитель: Имя Фамилия`
  - `эпик: Caller ID | проект: Онбординг | алиасы: caller id, caller`
  - `менеджер: Имя Фамилия`
  - `руководитель: Имя Фамилия`
  - `не Kaspi, а Онбординг`

## Mini App usage
- In Telegram, send `/app` to the bot.
- Open the Mini App from the inline button or menu button.
- The backend validates `initData`, reads your Telegram profile, and opens your personal workspace.
- Your projects, tasks, notes, drafts, and final reports are isolated by Telegram user.
- The first launch shows a short onboarding block directly in the Mini App.
- For local browser development outside Telegram, `./run_web.sh` still works as a dev shell, but personal auth only works inside Telegram Mini App launch flow.

## Jira import (offline, no API)
Recommended JQL:
```jql
resolution = Unresolved
AND (
  assignee = currentUser()
  OR reporter = currentUser()
  OR watcher = currentUser()
)
ORDER BY updated DESC
```

Export the filter from Jira as `CSV`, then import it:
```bash
source .venv/bin/activate
python -m delivery_reports.main import-jira /absolute/path/to/jira-export.csv --jira-base-url https://jira.example.com
```

Supported Jira CSV fields:
- `Issue key`
- `Summary`
- `Status`
- `Priority`
- `Assignee`
- `Reporter`
- `Updated`
- `Project name`
- `Project key`
- `Issue Type`
- `Epic Name` or similar epic columns
- `Labels`
- `Issue URL`

After import, the bot syncs epics from Jira rows and links them to projects when possible.

## Seed project directory
Edit [data/projects.sample.json](/Users/grafk1n/Documents/Delivery%20Reports%20/data/projects.sample.json) with your real projects and aliases.

## Privacy defaults
- Local SQLite storage.
- Local transcription path when Whisper is enabled.
- No external AI calls are hardwired into MVP.

## Structure
- `src/delivery_reports/config.py` runtime settings.
- `src/delivery_reports/db.py` schema and DB context.
- `src/delivery_reports/repository.py` persistence layer.
- `src/delivery_reports/services/parsing.py` note parsing.
- `src/delivery_reports/services/draft_builder.py` draft generation.
- `src/delivery_reports/services/transcription.py` voice transcription.
- `src/delivery_reports/bot_app.py` telegram handlers and scheduler.
- `docs/ARCHITECTURE.md` high-level architecture.
- `docs/MODULE_CONTRACTS.md` GRACE-lite module contracts.
