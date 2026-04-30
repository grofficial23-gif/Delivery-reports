from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from typing import Literal, Protocol

from ..repository import Note
from .errors import LLMInvalidResponse, LLMUnavailable
from .prompts import COMPOSE_JSON_SCHEMA, SYSTEM_PROMPT, TEMPLATE_LABELS
from .provider import LLMProvider, get_llm_provider

logger = logging.getLogger(__name__)

UpdateType = Literal["done", "plan", "risk", "blocker", "decision", "question", "note"]
ExcludeReason = Literal["duplicate", "low_signal", "false_risk", "false_blocker", "off_topic", "incomplete"]


class Update(Protocol):
    id: int
    note_date: str
    raw_text: str
    project_id: int | None
    done_text: str
    plan_text: str
    risk_text: str


@dataclass
class ComposedItem:
    project_id: int | None
    type: UpdateType
    text: str
    source_ids: list[int]
    salience: float


@dataclass
class ExcludedItem:
    source_id: int
    reason: ExcludeReason
    duplicate_of: int | None = None
    note: str | None = None


@dataclass
class ComposeResult:
    kept: list[ComposedItem]
    excluded: list[ExcludedItem]
    used_llm: bool
    fallback_reason: str | None


def smart_compose(
    updates: list[Update],
    template_key: str,
    user_lang: str = "ru",
    provider: LLMProvider | None = None,
) -> ComposeResult:
    if not _env_enabled("ENABLE_LLM_COMPOSE"):
        return _fallback_result(updates, "feature_flag_off")

    limit = _env_int("LLM_MAX_INPUT_UPDATES", 200)
    llm_updates = updates[:limit]
    overflow = updates[limit:]
    overflow_excluded = [
        ExcludedItem(
            source_id=int(update.id),
            reason="incomplete",
            duplicate_of=None,
            note="превышен лимит входа",
        )
        for update in overflow
    ]
    if overflow:
        logger.warning("LLM compose input truncated from %s to %s updates", len(updates), limit)

    try:
        llm_provider = provider or get_llm_provider()
    except LLMUnavailable as exc:
        logger.warning("LLM compose unavailable: %s", exc)
        reason = "no_api_key" if "api_key" in str(exc) or str(exc) == "no_api_key" else str(exc) or "unknown"
        return _fallback_result(updates, reason)

    user_prompt = build_user_prompt(llm_updates, template_key, user_lang)
    try:
        payload = llm_provider.complete_json(
            SYSTEM_PROMPT,
            user_prompt,
            COMPOSE_JSON_SCHEMA,
            max_output_tokens=2000,
            temperature=0.1,
        )
    except TimeoutError:
        logger.warning("LLM compose timeout")
        return _fallback_result(updates, "timeout")
    except LLMInvalidResponse as exc:
        logger.warning("LLM compose invalid response: %s", exc)
        return _fallback_result(updates, "invalid_json")
    except Exception as exc:
        logger.warning("LLM compose failed: %s", exc)
        return _fallback_result(updates, "unknown")

    valid_ids = {int(update.id) for update in llm_updates}
    kept: list[ComposedItem] = []
    for item in payload.get("kept", []):
        source_ids = [int(source_id) for source_id in item.get("source_ids", []) if int(source_id) in valid_ids]
        if not source_ids:
            continue
        kept.append(
            ComposedItem(
                project_id=item.get("project_id"),
                type=item.get("type", "note"),
                text=str(item.get("text", "")).strip(),
                source_ids=source_ids,
                salience=float(item.get("salience", 0.5)),
            )
        )

    if template_key == "concise":
        kept.sort(key=lambda item: item.salience, reverse=True)

    excluded = list(overflow_excluded)
    for item in payload.get("excluded", []):
        source_id = int(item.get("source_id", 0))
        if source_id not in valid_ids:
            continue
        duplicate_of = item.get("duplicate_of")
        if duplicate_of is not None and int(duplicate_of) not in valid_ids:
            duplicate_of = None
        excluded.append(
            ExcludedItem(
                source_id=source_id,
                reason=item.get("reason", "low_signal"),
                duplicate_of=int(duplicate_of) if duplicate_of is not None else None,
                note=item.get("note"),
            )
        )
    return ComposeResult(kept=kept, excluded=excluded, used_llm=True, fallback_reason=None)


def build_user_prompt(updates: list[Update], template_key: str, user_lang: str) -> str:
    report_date = next((getattr(update, "note_date", "") for update in updates if getattr(update, "note_date", "")), "")
    template_label = TEMPLATE_LABELS.get(template_key, template_key)
    lines = [
        f"Дата отчёта: {report_date or 'не указана'}",
        f"Шаблон: {template_key} ({template_label})",
        f"Язык: {user_lang}",
        "",
        "Апдейты сгруппированы по проектам:",
        "",
    ]
    for project_id, group in _group_updates(updates):
        project_title = "Без проекта" if project_id is None else f'Project {project_id}'
        lines.append(f"[{project_title}]")
        for update in group:
            lines.append(f"- id={update.id} [{_update_type(update)}] {_update_text(update)}")
        lines.append("")
    lines.append("Верни JSON по схеме.")
    return "\n".join(lines).strip()


def notes_for_renderer(updates: list[Note], result: ComposeResult) -> list[Note]:
    if not result.used_llm:
        return updates

    by_id = {note.id: note for note in updates}
    rendered: list[Note] = []
    for item in result.kept:
        source = by_id.get(item.source_ids[0])
        if source is None:
            continue
        rendered.append(_note_from_composed_item(source, item))
    return rendered


def serialize_compose_result(result: ComposeResult, updates: list[Note]) -> dict:
    text_by_id = {note.id: _update_text(note) for note in updates}
    return {
        "excluded": [
            {
                "source_id": item.source_id,
                "reason": item.reason,
                "duplicate_of": item.duplicate_of,
                "note": item.note,
                "text": text_by_id.get(item.source_id, ""),
                "duplicate_text": text_by_id.get(item.duplicate_of, "") if item.duplicate_of else "",
            }
            for item in result.excluded
        ],
        "used_llm": result.used_llm,
        "fallback_reason": result.fallback_reason,
    }


def _fallback_result(updates: list[Update], reason: str) -> ComposeResult:
    return ComposeResult(
        kept=[_composed_item_from_update(update) for update in updates],
        excluded=[],
        used_llm=False,
        fallback_reason=reason,
    )


def _composed_item_from_update(update: Update) -> ComposedItem:
    return ComposedItem(
        project_id=getattr(update, "project_id", None),
        type=_update_type(update),
        text=_update_text(update),
        source_ids=[int(update.id)],
        salience=0.5,
    )


def _note_from_composed_item(source: Note, item: ComposedItem) -> Note:
    done_text = ""
    plan_text = ""
    risk_text = ""
    if item.type == "plan":
        plan_text = item.text
    elif item.type == "risk":
        risk_text = item.text
    elif item.type == "blocker":
        risk_text = f"Блокер: {item.text}"
    elif item.type == "decision":
        done_text = item.text if item.text.lower().startswith("решение") else f"Решение — {item.text}"
    elif item.type == "question":
        done_text = item.text if item.text.lower().startswith("вопрос") else f"Вопрос — {item.text}"
    else:
        done_text = item.text
    return Note(
        id=source.id,
        note_date=source.note_date,
        user_id=source.user_id,
        source=source.source,
        raw_text=item.text,
        project_id=item.project_id,
        manager_name=source.manager_name,
        lead_name=source.lead_name,
        epic=source.epic,
        status_text=source.status_text,
        done_text=done_text,
        plan_text=plan_text,
        risk_text=risk_text,
        jira_links=source.jira_links,
        needs_review=source.needs_review,
    )


def _group_updates(updates: list[Update]) -> list[tuple[int | None, list[Update]]]:
    groups: dict[int | None, list[Update]] = {}
    for update in updates:
        groups.setdefault(getattr(update, "project_id", None), []).append(update)
    return sorted(groups.items(), key=lambda item: (item[0] is None, item[0] or 0))


def _update_type(update: Update) -> UpdateType:
    risk = getattr(update, "risk_text", "") or ""
    done = getattr(update, "done_text", "") or ""
    plan = getattr(update, "plan_text", "") or ""
    lowered_done = done.strip().lower()
    lowered_risk = risk.strip().lower()
    if lowered_risk.startswith(("блокер", "blocker")):
        return "blocker"
    if risk.strip():
        return "risk"
    if plan.strip() and not done.strip():
        return "plan"
    if lowered_done.startswith(("решение", "decision")):
        return "decision"
    if lowered_done.startswith(("вопрос", "question")):
        return "question"
    if done.strip():
        return "done"
    return "note"


def _update_text(update: Update) -> str:
    for attr in ("done_text", "plan_text", "risk_text", "raw_text"):
        value = (getattr(update, attr, "") or "").strip()
        if value:
            return " ".join(value.split())
    return ""


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
