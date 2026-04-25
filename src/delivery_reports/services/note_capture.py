from __future__ import annotations

from dataclasses import dataclass
from html import escape

from ..config import Settings
from ..repository import NewNote, Repository, UserProfile
from .parsing import ParsedNote, parse_note_blocks
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
            )
        )
    return results, unresolved_note_ids


def render_saved_note_message(result: StoredNoteResult) -> str:
    lines = [
        "<b>Заметка сохранена</b>",
        "",
        f"<b>Проект:</b> {escape(result.project_name)}",
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

    lines = [f"<b>Сообщение разделил на {len(results)} блока</b>", ""]
    for index, result in enumerate(results, start=1):
        lines.append(f"<b>{index}. {escape(result.project_name)}</b>")
        lines.append(f"- {'Нужно уточнить проект.' if result.needs_review else 'Сохранено.'}")
        if result.summary_line:
            lines.append(f"- {escape(result.summary_line)}")
    unresolved = [result for result in results if result.needs_review]
    if unresolved:
        last = unresolved[-1]
        lines.append("")
        lines.append("<b>Последний неуточненный блок</b>")
        lines.append("Можно просто ответить названием проекта.")
        if last.candidate_names:
            lines.append(f"<b>Варианты:</b> {escape(', '.join(last.candidate_names))}")
    return "\n".join(lines)


def short_summary_line(parsed: ParsedNote) -> str:
    for field in (parsed.done_text, parsed.plan_text, parsed.risk_text):
        if not field:
            continue
        first_line = field.splitlines()[0].strip()
        if first_line:
            return first_line
    return ""
