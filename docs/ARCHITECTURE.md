# Architecture (GRACE-lite)

## Goal
MVP focuses on daily PM report drafting from mixed input (text + voice) with local-first privacy.

## Layers
1. `Secure Intake`
   - Telegram text/voice messages.
   - No sensitive data leaves local runtime by default.
2. `Transcription`
   - Local Whisper-based voice-to-text.
3. `Normalization`
   - Project/epic detection, Jira link extraction, intent split (done/plan/risk).
4. `Draft Composer`
   - Builds one readable daily draft with common and special-control sections.
5. `Storage`
   - SQLite entities: projects, notes, drafts, final_reports, report_templates, app_state.
6. `Delivery`
   - Draft sent to owner in private Telegram chat.
   - Manual final send to group by user.
   - Optional final fixation in local DB for report history.

## RAG-ready decisions
- Every note has metadata (`date`, `source`, `project_id`, `epic`, `jira_links`).
- Structured fields are persisted (`done_text`, `plan_text`, `risk_text`) for future retrieval.
- Project aliases are explicit and editable, enabling later semantic routing/indexing.
- Draft and final versions are stored separately to support audit/reuse.
