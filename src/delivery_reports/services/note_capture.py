from __future__ import annotations

from dataclasses import dataclass
from html import escape

from ..config import Settings
from ..repository import NewNote, Repository, UserProfile
from .intent import (
    INTENT_KIND_OTHER,
    infer_intent_kind,
    label_for_kind,
    summarize_intents,
)
from .parsing import ParsedNote, parse_note_blocks
from .report_text_cleaner import clean_report_item_text
from .project_resolution import (
    fallback_project_ids,
    project_names_by_ids,
    resolve_lead_name,
    resolve_manager_name,
    resolve_project_for_block,
)


@dataclass
class StoredNoteResult:
    note_id: int
    project_name: str
    manager_name: str
    lead_name: str
    needs_review: bool
    candidate_names: list[str]
    summary_line: str
    intent_kind: str = INTENT_KIND_OTHER


def store_notes(
    repository: Repository,
    settings: Settings,
    raw_text: str,
    note_date: str,
    source: str,
    user: UserProfile,
    transcript_text: str = "",
) -> tuple[list[StoredNoteResult], list[int]]:
    projects = repository.list_projects(owner_user_id=user.telegram_user_id)
    parsed_blocks = parse_note_blocks(raw_text, projects)
    results: list[StoredNoteResult] = []
    unresolved_note_ids: list[int] = []
    fallback_ids = fallback_project_ids(repository, owner_user_id=user.telegram_user_id)

    for block in parsed_blocks:
        parsed = block.parsed
        resolution = resolve_project_for_block(
            repository=repository,
            block_text=block.raw_text,
            parsed_note=parsed,
            fallback_project_ids=fallback_ids,
            owner_user_id=user.telegram_user_id,
        )
        project = repository.get_project(resolution.project_id, owner_user_id=user.telegram_user_id) if resolution.project_id else None
        needs_review = resolution.project_id is None
        manager_name = resolve_manager_name(project, user, settings)
        lead_name = resolve_lead_name(project, user, settings)
        note = NewNote(
            note_date=note_date,
            user_id=user.telegram_user_id,
            source=source,
            raw_text=block.raw_text,
            transcript_text=transcript_text,
            project_id=resolution.project_id,
            manager_name=manager_name,
            lead_name=lead_name,
            epic=parsed.epic,
            status_text=parsed.status_text,
            done_text=parsed.done_text,
            plan_text=parsed.plan_text,
            risk_text=parsed.risk_text,
            jira_links=parsed.jira_links,
            needs_review=needs_review,
        )
        note_id = repository.add_note(note)
        if project is not None and parsed.epic:
            repository.upsert_epic(project.id, parsed.epic, aliases=[parsed.epic], source="note")
        if needs_review:
            unresolved_note_ids.append(note_id)
        intent_kind = infer_intent_kind(
            done_text=parsed.done_text,
            plan_text=parsed.plan_text,
            risk_text=parsed.risk_text,
            needs_review=needs_review,
        )
        results.append(
            StoredNoteResult(
                note_id=note_id,
                project_name=project.name if project else "Не уверен",
                manager_name=manager_name,
                lead_name=lead_name,
                needs_review=needs_review,
                candidate_names=project_names_by_ids(
                    repository,
                    resolution.candidate_project_ids,
                    owner_user_id=user.telegram_user_id,
                ),
                summary_line=short_summary_line(parsed),
                intent_kind=intent_kind,
            )
        )
    return results, unresolved_note_ids


def render_saved_note_message(result: StoredNoteResult) -> str:
    intent_label = label_for_kind(result.intent_kind)
    project_display = _project_display(result)
    lines = [
        "<b>Заметка сохранена</b>",
        "",
        f"<b>{escape(intent_label)} · {escape(project_display)}</b>",
        f"<b>Менеджер:</b> {escape(result.manager_name or '-')}",
        f"<b>Руководитель:</b> {escape(result.lead_name or '-')}",
    ]
    if result.summary_line:
        lines.append(f"<b>Что понял:</b> {escape(result.summary_line)}")
    if result.needs_review:
        lines.append("")
        lines.append("<b>Нужно уточнить проект</b>")
        if result.candidate_names:
            lines.append(f"<b>Варианты:</b> {escape(', '.join(result.candidate_names))}")
        else:
            lines.append("Варианты проекта пока не нашлись автоматически.")
        lines.append("Можно ответить названием проекта или сообщением <code>проект: Название</code>.")
    return "\n".join(lines)


def render_saved_notes_message(results: list[StoredNoteResult]) -> str:
    if len(results) == 1:
        return render_saved_note_message(results[0])

    block_word = _pluralize_blocks(len(results))
    lines = [f"<b>Сообщение разделил на {len(results)} {block_word}</b>"]
    summary = summarize_intents([result.intent_kind for result in results])
    if summary:
        lines.append(escape(summary))
    lines.append("")
    for index, result in enumerate(results, start=1):
        intent_label = label_for_kind(result.intent_kind)
        project_part = _project_display(result)
        lines.append(
            f"<b>{index}. {escape(intent_label)} · {escape(project_part)}</b>"
        )
        if result.summary_line:
            lines.append(f"- {escape(result.summary_line)}")
        elif result.needs_review and result.candidate_names:
            lines.append(
                f"- Варианты: {escape(', '.join(result.candidate_names))}"
            )
    unresolved = [result for result in results if result.needs_review]
    if unresolved:
        last = unresolved[-1]
        lines.append("")
        lines.append("<b>Последний неуточненный блок</b>")
        lines.append("Можно просто ответить названием проекта.")
        if last.candidate_names:
            lines.append(f"<b>Варианты:</b> {escape(', '.join(last.candidate_names))}")
    return "\n".join(lines)


def _project_display(result: StoredNoteResult) -> str:
    """Display name for the project on the bot reply.

    When the project couldn't be resolved (`needs_review=True` with the
    sentinel "Не уверен" / "" name), show the explicit
    "📥 Нужно уточнить проект" hint.  Otherwise the actual project name
    wins so the user immediately sees that auto-matching worked.
    """
    name = (result.project_name or "").strip()
    if result.needs_review and name in ("", "Не уверен"):
        return "📥 Нужно уточнить проект"
    return name or "Без проекта"


def _pluralize_blocks(count: int) -> str:
    last_two = count % 100
    last_one = count % 10
    if 11 <= last_two <= 14:
        return "блоков"
    if last_one == 1:
        return "блок"
    if 2 <= last_one <= 4:
        return "блока"
    return "блоков"


def short_summary_line(parsed: ParsedNote) -> str:
    for field in (parsed.done_text, parsed.plan_text, parsed.risk_text):
        if not field:
            continue
        first_line = field.splitlines()[0].strip()
        cleaned = clean_report_item_text(first_line)
        if cleaned:
            return cleaned
        if first_line:
            return first_line
    return ""
