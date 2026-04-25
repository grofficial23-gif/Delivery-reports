# Module Contracts (GRACE-lite)

## `config.py`
- Input: environment variables (`.env`).
- Output: immutable `Settings`.
- Contract: all runtime configuration resolved in one place.

## `db.py`
- Input: database path.
- Output: initialized SQLite schema + connection context manager.
- Contract: schema creation is idempotent.

## `repository.py`
- Input: domain-level data from handlers/services.
- Output: stored/retrieved structured entities.
- Contract: persistence is centralized; handlers never build SQL.
- Notes: stores notes, drafts, final reports, app state, and report templates.

## `services/parsing.py`
- Input: raw note text + project directory.
- Output: `ParsedNote` with project guess, epic, done/plan/risk, Jira links.
- Contract: parsing is deterministic and side-effect free.

## `services/transcription.py`
- Input: path to audio file.
- Output: transcript string.
- Contract: returns empty string on failure; caller handles fallback.

## `services/draft_builder.py`
- Input: date + notes + projects + defaults.
- Output: human-readable daily draft.
- Contract: one message format, stable and extensible.
- Notes: supports style modes (`standard`, `concise`, `risk_focus`, `team_examples`).

## `bot_app.py`
- Input: Telegram updates.
- Output: user-facing bot actions + repository writes.
- Contract: orchestrates use-cases only; no raw SQL and no heavy parsing logic.
- Notes: supports draft/final flows, template selection, and retry parsing for unresolved notes.

## `main.py`
- Input: none.
- Output: fully initialized running bot process.
- Contract: bootstraps dependencies and starts polling loop.
