from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from html import escape

from ..repository import Note, Project
from .report_presenter import compact_section_items, limit_section_items
from .report_text_cleaner import clean_report_item_text


def _tpl(value: str) -> str:
    """Wrap a template/placeholder value so it stands out in Telegram HTML.

    Renders as: ✏️ <i>value</i>  — signals to the PM that this was
    auto-filled and may need manual correction before sending.
    """
    return f"\u270f\ufe0f <i>{escape(value)}</i>"


@dataclass
class ProjectAggregate:
    project: Project
    epics: set[str] = field(default_factory=set)
    explicit_statuses: list[str] = field(default_factory=list)
    done_items: list[str] = field(default_factory=list)
    plan_items: list[str] = field(default_factory=list)
    risk_items: list[str] = field(default_factory=list)
    blocker_items: list[str] = field(default_factory=list)
    decision_items: list[str] = field(default_factory=list)
    question_items: list[str] = field(default_factory=list)
    jira_links: set[str] = field(default_factory=set)
    needs_review_count: int = 0


def build_daily_draft(
    target_date: date,
    notes: list[Note],
    projects: list[Project],
    default_manager_name: str,
    default_lead_name: str,
    style: str = "standard",
) -> str:
    header_manager = _select_common_value(
        [note.manager_name for note in notes if note.manager_name],
        default_manager_name,
    )
    header_lead = _select_common_value(
        [note.lead_name for note in notes if note.lead_name],
        default_lead_name,
    )
    project_by_id = {project.id: project for project in projects}
    fallback_project = Project(
        id=0,
        owner_user_id=0,
        name="Без проекта",
        manager_name=header_manager,
        lead_name=header_lead,
        jira_base_url="",
        aliases=[],
        is_special_control=False,
    )
    grouped: dict[str, ProjectAggregate] = {}
    for note in notes:
        project = project_by_id.get(note.project_id) if note.project_id else None
        group_key: str
        if not project:
            if note.epic:
                project = Project(
                    id=0,
                    owner_user_id=0,
                    name=note.epic,
                    manager_name=note.manager_name or header_manager,
                    lead_name=note.lead_name or header_lead,
                    jira_base_url="",
                    aliases=[],
                    is_special_control=False,
                )
                group_key = f"epic:{note.epic.lower()}"
            else:
                project = fallback_project
                group_key = "unknown"
        else:
            group_key = f"project:{project.id}"
        aggregate = grouped.get(group_key)
        if aggregate is None:
            grouped[group_key] = ProjectAggregate(project=project)
            aggregate = grouped[group_key]
        if note.epic:
            aggregate.epics.add(note.epic)
        if note.status_text.strip():
            aggregate.explicit_statuses.append(note.status_text.strip())
        _route_done_lines(
            aggregate.done_items,
            aggregate.decision_items,
            aggregate.question_items,
            note.done_text,
        )
        _append_lines(aggregate.plan_items, note.plan_text)
        _route_risk_lines(aggregate.risk_items, aggregate.blocker_items, note.risk_text)
        for link in note.jira_links:
            aggregate.jira_links.add(link)
        if note.needs_review:
            aggregate.needs_review_count += 1

    common_projects: list[ProjectAggregate] = []
    special_projects: list[ProjectAggregate] = []
    for aggregate in grouped.values():
        if aggregate.project.is_special_control:
            special_projects.append(aggregate)
        else:
            common_projects.append(aggregate)

    common_projects.sort(key=lambda item: item.project.name.lower())
    special_projects.sort(key=lambda item: item.project.name.lower())

    title_date = target_date.strftime("%d.%m.%Y")
    if style == "team_examples":
        return _render_team_examples_draft(
            title_date=title_date,
            header_manager=header_manager,
            header_lead=header_lead,
            common_projects=common_projects,
            special_projects=special_projects,
        )

    lines: list[str] = []
    lines.append("<b>Общие апдейты</b>")
    lines.append(f"<b>Дата:</b> {escape(title_date)}")
    manager_val = header_manager or "-"
    lead_val = header_lead or "-"
    is_default_manager = not header_manager or header_manager == default_manager_name
    is_default_lead = not header_lead or header_lead == default_lead_name
    lines.append(f"<b>Менеджер:</b> {_tpl(manager_val) if is_default_manager else escape(manager_val)}")
    lines.append(f"<b>Руководитель:</b> {_tpl(lead_val) if is_default_lead else escape(lead_val)}")
    lines.append("")
    if common_projects:
        for index, aggregate in enumerate(common_projects, start=1):
            lines.extend(_render_project_block(index, aggregate, style))
    else:
        lines.append("За сегодня заметки по общим апдейтам не добавлены.")

    if special_projects:
        lines.append("")
        lines.append("<b>Особый контроль</b>")
        lines.append(f"<b>Дата:</b> {escape(title_date)}")
        lines.append(f"<b>Менеджер:</b> {_tpl(manager_val) if is_default_manager else escape(manager_val)}")
        lines.append(f"<b>Руководитель:</b> {_tpl(lead_val) if is_default_lead else escape(lead_val)}")
        lines.append("")
        for index, aggregate in enumerate(special_projects, start=1):
            lines.extend(_render_project_block(index, aggregate, style))

    return "\n".join(lines).strip()


def build_weekly_summary(
    start_date: date,
    end_date: date,
    notes: list[Note],
    projects: list[Project],
    team_name: str
) -> str:
    """Builds a weekly executive summary for a team's activity."""
    project_by_id = {project.id: project for project in projects}
    fallback_project = Project(
        id=0, owner_user_id=0, name="Без проекта", manager_name="", lead_name="", jira_base_url="", aliases=[], is_special_control=False
    )
    
    grouped: dict[str, ProjectAggregate] = {}
    for note in notes:
        project = project_by_id.get(note.project_id) if note.project_id else None
        if not project:
            project = fallback_project
        group_key = f"project:{project.id}"
        
        aggregate = grouped.get(group_key)
        if aggregate is None:
            grouped[group_key] = ProjectAggregate(project=project)
            aggregate = grouped[group_key]
        
        _route_done_lines(
            aggregate.done_items,
            aggregate.decision_items,
            aggregate.question_items,
            note.done_text,
        )
        _append_lines(aggregate.plan_items, note.plan_text)
        _route_risk_lines(aggregate.risk_items, aggregate.blocker_items, note.risk_text)

    lines: list[str] = []
    lines.append(f"📈 <b>Weekly Executive Summary: {escape(team_name)}</b>")
    lines.append(f"<b>Период:</b> {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}")
    lines.append(f"<b>Сотрудников с отчетами:</b> {len(set(note.user_id for note in notes))}")
    lines.append("")

    if not grouped:
        lines.append("За прошедшую неделю команда не оставила ни одного апдейта.")
        return "\n".join(lines).strip()

    for index, aggregate in enumerate(sorted(grouped.values(), key=lambda a: a.project.name.lower()), start=1):
        done_items = _limit_items(_compact_items(_clean_items(aggregate.done_items + aggregate.decision_items), "done"), "standard", "done")
        risk_items = _limit_items(_compact_items(_clean_items(aggregate.risk_items + aggregate.blocker_items), "risk"), "standard", "risk")
        
        lines.append(f"<b>{index}. {escape(aggregate.project.name)}</b>")
        if done_items:
            lines.append("<b>Что сделано:</b>")
            lines.extend(_render_bullets(done_items))
        if risk_items and not _risk_items_are_empty(risk_items):
            lines.append(f"<b>{_risk_label(risk_items)}:</b>")
            lines.extend(_render_bullets(risk_items))
        lines.append("")

    lines.append("<i>Сгенерировано автоматически (PM Digest TEAM)</i>")
    return "\n".join(lines).strip()


def _render_team_examples_draft(
    title_date: str,
    header_manager: str,
    header_lead: str,
    common_projects: list[ProjectAggregate],
    special_projects: list[ProjectAggregate],
) -> str:
    lines: list[str] = [
        f"<b>Дата:</b> {escape(title_date)}",
        f"<b>Менеджер:</b> {_tpl(header_manager) if not header_manager or header_manager == header_manager else escape(header_manager)}",
        f"<b>Руководитель:</b> {escape(header_lead) if header_lead else _tpl('-')}",
        "",
    ]

    if common_projects:
        for index, aggregate in enumerate(common_projects, start=1):
            lines.extend(_render_team_examples_project_block(index, aggregate))
    else:
        lines.append("За сегодня заметки не добавлены.")

    if special_projects:
        lines.append("")
        lines.append("<b>Особый контроль</b>")
        lines.append("")
        for index, aggregate in enumerate(special_projects, start=1):
            lines.extend(_render_team_examples_project_block(index, aggregate))

    return "\n".join(lines).strip()


def _append_lines(buffer: list[str], block_text: str | None) -> None:
    if not block_text:
        return
    for line in (part.strip("-• \t") for part in block_text.splitlines()):
        if line:
            buffer.append(line)


def _route_done_lines(
    done_buffer: list[str],
    decision_buffer: list[str],
    question_buffer: list[str],
    block_text: str | None,
) -> None:
    """Split note.done_text lines into done / decision / question buckets.

    The parser injects synthetic prefixes ("решение —", "вопрос —") on
    atomic items.  Honor those here so the draft can render dedicated
    "◆ Решение" and "❓ Вопросы" sections.
    """
    if not block_text:
        return
    for line in (part.strip("-• \t") for part in block_text.splitlines()):
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith(("решение —", "решение -")):
            decision_buffer.append(line)
        elif lowered.startswith(("вопрос —", "вопрос -")):
            question_buffer.append(line)
        else:
            done_buffer.append(line)


def _route_risk_lines(
    risk_buffer: list[str],
    blocker_buffer: list[str],
    block_text: str | None,
) -> None:
    """Split note.risk_text lines into risk / blocker buckets."""
    if not block_text:
        return
    for line in (part.strip("-• \t") for part in block_text.splitlines()):
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith(("блокер —", "блокер -")) or lowered.startswith("блокер:"):
            blocker_buffer.append(line)
        else:
            risk_buffer.append(line)


def _clean_items(items: list[str]) -> list[str]:
    """Apply clean_report_item_text to every item, dropping empties.

    Empties happen when the line was a pure project label
    ("Проект: Delivery.") or a leftover synthetic prefix.
    """
    cleaned: list[str] = []
    for item in items:
        out = clean_report_item_text(item)
        if out:
            cleaned.append(out)
    return cleaned


def _cross_section_norm_key(text: str) -> str:
    """Normalize bullet text for duplicate detection across sections."""
    base = clean_report_item_text(text) or (text or "").strip()
    t = base.strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = t.replace("×", "x")
    return t.rstrip(".!?…")


def _dedupe_sections_in_priority_order(
    *,
    blocker_items: list[str],
    risk_items: list[str],
    decision_items: list[str],
    done_items: list[str],
    plan_items: list[str],
    question_items: list[str],
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str]]:
    """If the same bullet appears in multiple sections, keep the highest-priority copy.

    Priority: blocker > risk > decision > done > plan > question
    """
    seen: set[str] = set()

    def _take(items: list[str]) -> list[str]:
        out: list[str] = []
        for item in items:
            key = _cross_section_norm_key(item)
            if not key:
                out.append(item)
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    return (
        _take(blocker_items),
        _take(risk_items),
        _take(decision_items),
        _take(done_items),
        _take(plan_items),
        _take(question_items),
    )


def _render_modern_bullets(items: list[str]) -> list[str]:
    """Render bullets in the demo-ready format (• prefix, normalized end)."""
    return [f"• {escape(_normalize_sentence(item))}" for item in items]


def _select_common_value(values: list[str], fallback: str) -> str:
    if not values:
        return fallback
    counted = Counter(values)
    return counted.most_common(1)[0][0]


def _render_project_block(index: int, aggregate: ProjectAggregate, style: str) -> list[str]:
    """Render one project section in the demo-ready emoji format.

    Sections are skipped entirely when empty — no "- нет" filler.
    Each bullet is run through clean_report_item_text() to strip
    synthetic prefixes ("блокер —", "вопрос —") and user-typed labels
    ("Блокер по Bank Dashboard:") so the reader sees only the actual
    content.
    """
    done_items = _limit_items(_compact_items(_clean_items(aggregate.done_items), "done"), style, "done")
    plan_items = _limit_items(_compact_items(_clean_items(aggregate.plan_items), "plan"), style, "plan")
    risk_items = _limit_items(_compact_items(_clean_items(aggregate.risk_items), "risk"), style, "risk")
    blocker_items = _limit_items(_compact_items(_clean_items(aggregate.blocker_items), "blocker"), style, "blocker")
    decision_items = _limit_items(_compact_items(_clean_items(aggregate.decision_items), "decision"), style, "decision")
    question_items = _limit_items(_compact_items(_clean_items(aggregate.question_items), "question"), style, "question")

    blocker_items, risk_items, decision_items, done_items, plan_items, question_items = (
        _dedupe_sections_in_priority_order(
            blocker_items=blocker_items,
            risk_items=risk_items,
            decision_items=decision_items,
            done_items=done_items,
            plan_items=plan_items,
            question_items=question_items,
        )
    )

    if _risk_items_are_empty(risk_items):
        risk_items = []
    if _risk_items_are_empty(blocker_items):
        blocker_items = []

    is_unresolved = aggregate.project.name.strip().lower() == "без проекта"
    title_emoji = "📥" if is_unresolved else "📌"
    title_text = "Нужно уточнить проект" if is_unresolved else aggregate.project.name

    lines: list[str] = []
    lines.append(f"{title_emoji} <b>{escape(title_text)}</b>")
    if aggregate.epics and not _is_epic_promoted_to_title(aggregate):
        lines.append(f"<b>Эпик:</b> {escape(', '.join(sorted(aggregate.epics)))}")
    lines.append(
        f"<b>Статус:</b> {escape(_resolve_status_line(aggregate, done_items, plan_items, risk_items + blocker_items, style, question_items))}"
    )

    # Per-style section order. concise = "Только главное" trims everything;
    # risk_focus = "Для руководителя" surfaces problems first; standard =
    # "Баланс" shows the full picture; team_examples uses a separate path.
    if style == "risk_focus":
        section_order = [
            ("⛔ Блокеры", "blocker", blocker_items),
            ("⚠️ Риски", "risk", risk_items),
            ("◆ Решение", "decision", decision_items),
            ("✅ Что сделано", "done", done_items),
            ("🧭 План", "plan", plan_items),
            ("❓ Вопросы", "question", question_items),
        ]
    elif style == "concise":
        section_order = [
            ("⛔ Блокеры", "blocker", blocker_items),
            ("✅ Что сделано", "done", done_items),
            ("🧭 План", "plan", plan_items),
            ("⚠️ Риски", "risk", risk_items),
        ]
    else:  # standard ("Баланс") — full picture
        section_order = [
            ("✅ Что сделано", "done", done_items),
            ("◆ Решение", "decision", decision_items),
            ("🧭 План", "plan", plan_items),
            ("⚠️ Риски", "risk", risk_items),
            ("❓ Вопросы", "question", question_items),
            ("⛔ Блокеры", "blocker", blocker_items),
        ]

    for label, _key, items in section_order:
        if not items:
            continue
        lines.append("")
        lines.append(f"<b>{label}</b>")
        lines.extend(_render_modern_bullets(items))

    if aggregate.jira_links:
        lines.append("")
        lines.append(f"<b>Jira:</b> {_render_links(sorted(aggregate.jira_links))}")

    if aggregate.needs_review_count and not is_unresolved:
        lines.append("")
        lines.append(f"<b>Нужно уточнить:</b> автопривязка заметок ({aggregate.needs_review_count})")

    lines.append("")
    return lines


def _render_team_examples_project_block(index: int, aggregate: ProjectAggregate) -> list[str]:
    done_items = _limit_items(_compact_items(_clean_items(aggregate.done_items + aggregate.decision_items + aggregate.question_items), "done"), "team_examples", "done")
    plan_items = _limit_items(_compact_items(_clean_items(aggregate.plan_items), "plan"), "team_examples", "plan")
    risk_items = _limit_items(_compact_items(_clean_items(aggregate.risk_items + aggregate.blocker_items), "risk"), "team_examples", "risk")
    if _risk_items_are_empty(risk_items):
        risk_items = []
    lines: list[str] = []

    title = f"<b>{index}. {escape(aggregate.project.name)}</b>"
    jira_suffix = _render_inline_links_suffix(sorted(aggregate.jira_links))
    if jira_suffix:
        title = f"{title} {jira_suffix}"
    lines.append(title)

    if aggregate.epics and not _is_epic_promoted_to_title(aggregate):
        lines.append(f"<b>Эпик:</b> {escape(', '.join(sorted(aggregate.epics)))}")

    lines.append(
        f"<b>Статус:</b> {escape(_resolve_status_line(aggregate, done_items, plan_items, risk_items, 'team_examples'))}"
    )

    if done_items:
        lines.append("")
        lines.append("<b>Что сделано:</b>")
        lines.extend(_render_bullets(done_items))

    if plan_items:
        lines.append("")
        lines.append(f"<b>{_team_plan_label(plan_items)}:</b>")
        lines.extend(_render_bullets(plan_items))

    lines.append("")
    if not risk_items:
        lines.append("<b>Риск:</b> нет.")
    else:
        lines.append(f"<b>{_risk_label(risk_items)}:</b>")
        lines.extend(_render_bullets(risk_items))

    if aggregate.needs_review_count:
        lines.append("")
        lines.append(f"<b>Нужно уточнить:</b> автопривязка заметок ({aggregate.needs_review_count})")

    lines.append("")
    return lines


def _compact_items(items: list[str], section: str) -> list[str]:
    return compact_section_items(items, section=section)


def _resolve_status_line(
    aggregate: ProjectAggregate,
    done_items: list[str],
    plan_items: list[str],
    risk_items: list[str],
    style: str,
    question_items: list[str] | None = None,
) -> str:
    if aggregate.explicit_statuses:
        return _select_common_value(aggregate.explicit_statuses, aggregate.explicit_statuses[0])
    return _build_status_line(done_items, plan_items, risk_items, style, question_items or [])


def _build_status_line(
    done_items: list[str],
    plan_items: list[str],
    risk_items: list[str],
    style: str,
    question_items: list[str],
) -> str:
    # Executive verdict: any blocker/risk/question → "Требует внимания".
    if style == "risk_focus" and (risk_items or question_items):
        return "Требует внимания."
    if done_items and _looks_completed(done_items) and not plan_items:
        return "Завершено."
    if done_items or plan_items:
        return "В работе."
    if risk_items:
        return "Есть блокеры."
    return "\u270f\ufe0f <i>Уточняется.</i>"


def _render_plan_section(plan_items: list[str]) -> list[str]:
    if not plan_items:
        return []
    return ["<b>План на завтра:</b>", *_render_bullets(plan_items)]


def _render_risk_section(risk_items: list[str]) -> list[str]:
    if not risk_items:
        return ["<b>Риски:</b>", "- нет"]
    return [f"<b>{_risk_label(risk_items)}:</b>", *_render_bullets(risk_items)]


def _render_bullets(items: list[str]) -> list[str]:
    return [f"- {escape(_normalize_sentence(item))}" for item in items]


def _risk_label(risk_items: list[str]) -> str:
    if len(risk_items) == 1:
        return "Риск"
    return "Риски"


def _risk_items_are_empty(risk_items: list[str]) -> bool:
    if not risk_items:
        return True
    empty_markers = {"нет", "нет.", "отсутствуют", "отсутствует", "без изменений", "none", "-"}
    cleaned = {item.strip().lower() for item in risk_items if item.strip()}
    return bool(cleaned) and cleaned.issubset(empty_markers)


def _team_plan_label(plan_items: list[str]) -> str:
    if any(any(token in item.lower() for token in ("недел", "след")) for item in plan_items):
        return "Планы на завтра / след. неделю"
    if len(plan_items) > 1:
        return "Планы на завтра"
    return "План на завтра"


def _limit_items(items: list[str], style: str, section: str) -> list[str]:
    return limit_section_items(items, section=section, style=style)


def _looks_completed(items: list[str]) -> bool:
    markers = ("заверш", "готов", "выполн", "закрыт", "релизн", "отправлен")
    for item in items:
        lowered = item.lower()
        if any(marker in lowered for marker in markers):
            return True
    return False


def _normalize_sentence(text: str) -> str:
    value = text.strip()
    if not value:
        return ""
    value = value.rstrip(" ;,")
    if not value.endswith((".", "!", "?")):
        value += "."
    return value[0].upper() + value[1:]


def _is_epic_promoted_to_title(aggregate: ProjectAggregate) -> bool:
    if len(aggregate.epics) != 1:
        return False
    epic = next(iter(aggregate.epics))
    return epic.strip().lower() == aggregate.project.name.strip().lower()


def _render_links(links: list[str]) -> str:
    rendered = []
    for index, link in enumerate(links[:3], start=1):
        rendered.append(f'<a href="{escape(link, quote=True)}">Jira {index}</a>')
    if len(links) > 3:
        rendered.append(f"и еще {len(links) - 3}")
    return ", ".join(rendered)


def _render_inline_links_suffix(links: list[str]) -> str:
    rendered = _render_links(links)
    if not rendered:
        return ""
    return f"| {rendered}"
