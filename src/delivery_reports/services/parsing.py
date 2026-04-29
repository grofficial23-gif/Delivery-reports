from __future__ import annotations

from dataclasses import dataclass, field
import re

from ..repository import Project
from ..shared import JIRA_KEY_RE
from .long_update_split import (
    AtomicUpdate,
    looks_long_unstructured,
    split_long_update,
)
from .report_text_cleaner import clean_report_item_text, pre_clean_incoming_report_text


JIRA_LINK_RE = re.compile(r"https?://\S+/browse/[A-Z][A-Z0-9]+-\d+", re.IGNORECASE)


@dataclass
class ParsedNote:
    project_id: int | None
    candidate_project_ids: list[int] = field(default_factory=list)
    epic: str = ""
    status_text: str = ""
    done_text: str = ""
    plan_text: str = ""
    risk_text: str = ""
    jira_links: list[str] = field(default_factory=list)
    needs_review: bool = False


@dataclass
class ParsedNoteBlock:
    raw_text: str
    parsed: ParsedNote


def parse_note_text(raw_text: str, projects: list[Project]) -> ParsedNote:
    raw_text = pre_clean_incoming_report_text(raw_text)
    jira_links = _extract_jira_links(raw_text, projects)
    project_id, candidate_project_ids, needs_review = _detect_project(raw_text, projects)
    epic = _extract_epic(raw_text)
    status_text, done_text, plan_text, risk_text = _split_by_intent(raw_text)
    return ParsedNote(
        project_id=project_id,
        candidate_project_ids=candidate_project_ids,
        epic=epic,
        status_text=status_text,
        done_text=done_text,
        plan_text=plan_text,
        risk_text=risk_text,
        jira_links=jira_links,
        needs_review=needs_review,
    )


def parse_note_blocks(raw_text: str, projects: list[Project]) -> list[ParsedNoteBlock]:
    raw_text = pre_clean_incoming_report_text(raw_text)
    blocks = _split_into_blocks(raw_text, projects)
    if (
        len(blocks) == 1
        and not _has_explicit_section_markers(blocks[0])
        and looks_long_unstructured(blocks[0])
    ):
        atoms = split_long_update(blocks[0], projects)
        if len(atoms) >= 2:
            return [_atomic_to_block(atom, projects) for atom in atoms]
    return [ParsedNoteBlock(raw_text=block, parsed=parse_note_text(block, projects)) for block in blocks]


# ── Long-update integration helpers ───────────────────────────────────


_INTENT_TO_PREFIX: dict[str, str] = {
    # Re-uses existing _split_by_intent keyword routing to avoid duplicating
    # field-mapping logic.
    "done": "Что сделано: ",
    "plan": "План: ",
    "risk": "Риск: ",
    "blocker": "Риск: блокер — ",
    "decision": "Что сделано: решение — ",
    "question": "Что сделано: вопрос — ",
    "other": "",
}


def _atomic_to_block(atom: AtomicUpdate, projects: list[Project]) -> ParsedNoteBlock:
    prefix = _INTENT_TO_PREFIX.get(atom.intent, "")
    virtual_lines: list[str] = []
    if atom.project_name_hint:
        virtual_lines.append(f"Проект: {atom.project_name_hint}")
    # Pre-clean: first strip "По <known-project>" from the start, then run
    # the generic cleaner.  This removes user-typed leading labels like
    # "Блокер по Bank Dashboard:" AND voice-dictation intros like
    # "По Delivery Reports сделал …".  Together they guarantee the stored
    # text never duplicates marker nesting like "блокер — Блокер по …".
    body_pre = _strip_leading_project_intro(atom.text, projects)
    body_clean = clean_report_item_text(body_pre)
    body = body_clean or body_pre.strip()
    virtual_lines.append(f"{prefix}{body}" if prefix else body)
    virtual_text = "\n".join(virtual_lines)
    parsed = parse_note_text(virtual_text, projects)
    return ParsedNoteBlock(raw_text=atom.text.strip(), parsed=parsed)


def _strip_leading_project_intro(text: str, projects: list[Project]) -> str:
    """Remove a leading 'По <ProjectName>' / 'По <alias>' from *text*.

    Only strips when the candidate matches a known project name or alias
    exactly.  Tries the longest candidate first so phrase aliases
    ("Bank Dashboard") win over single-word ones ("Bank").  Returns the
    text unchanged when no candidate matches.
    """
    if not text:
        return text
    lowered = text.lower().lstrip()
    if not lowered.startswith("по "):
        return text
    candidates: list[str] = []
    for project in projects:
        name = (project.name or "").strip()
        if not name or name.lower() == "без проекта":
            continue
        candidates.append(name)
        for alias in project.aliases or ():
            alias_clean = (alias or "").strip()
            if alias_clean:
                candidates.append(alias_clean)
    candidates.sort(key=len, reverse=True)
    stripped_text = text.lstrip()
    leading_ws = text[: len(text) - len(stripped_text)]
    stripped_lower = stripped_text.lower()
    for candidate in candidates:
        prefix = f"по {candidate.lower()}"
        if stripped_lower.startswith(prefix):
            tail = stripped_text[len(prefix):]
            tail_stripped = tail.lstrip(" \t,:;.-—")
            return f"{leading_ws}{tail_stripped}" if tail_stripped else ""
    return text


def _has_explicit_section_markers(text: str) -> bool:
    """True if the text uses *heading-style* section markers.

    We only trip on actual headings — e.g. a line starting with
    "Что сделано:" / "План:" / "Проект:" — NOT on the same words appearing
    inside a free-form sentence ("план на завтра demo").
    """
    heading_prefixes = (
        "что сделано", "сделано за сегодня",
        "план на завтра", "планы на завтра",
        "план:", "планы:",
        "риск:", "риски:", "блокер:", "блокеры:",
        "статус:", "проект:", "эпик:", "дата:",
        "менеджер:", "руководитель:",
    )
    for line in text.splitlines():
        lowered = line.strip().lower().lstrip("-•* \t")
        if not lowered:
            continue
        if any(lowered.startswith(prefix) for prefix in heading_prefixes):
            return True
    return False


def _extract_jira_links(raw_text: str, projects: list[Project]) -> list[str]:
    links = set(link.strip(".,;") for link in JIRA_LINK_RE.findall(raw_text))
    jira_keys = set(match.group(1).upper() for match in JIRA_KEY_RE.finditer(raw_text))
    if jira_keys:
        for key in jira_keys:
            prefix = key.split("-")[0]
            base_url = _find_base_url_for_prefix(prefix, projects)
            if base_url:
                links.add(f"{base_url.rstrip('/')}/browse/{key}")
    return sorted(links)


def _find_base_url_for_prefix(prefix: str, projects: list[Project]) -> str:
    for project in projects:
        if not project.jira_base_url:
            continue
        for alias in project.aliases:
            if alias.upper() == prefix:
                return project.jira_base_url
    return ""


def _detect_project(raw_text: str, projects: list[Project]) -> tuple[int | None, list[int], bool]:
    text = raw_text.lower()
    scored_matches: list[tuple[int, int]] = []
    for project in projects:
        if project.name.lower() == "без проекта":
            continue
        score = 0
        if project.name and project.name.lower() in text:
            score += 6
        for alias in project.aliases:
            alias_clean = alias.strip().lower()
            if not alias_clean:
                continue
            if alias_clean in text:
                score += 3
        if score > 0:
            scored_matches.append((project.id, score))

    if not scored_matches:
        fallback_ids = [project.id for project in projects if project.name.lower() != "без проекта"][:3]
        return None, fallback_ids, True

    scored_matches.sort(key=lambda item: item[1], reverse=True)
    candidate_ids = [project_id for project_id, _score in scored_matches[:3]]
    best_project_id, best_score = scored_matches[0]
    second_score = scored_matches[1][1] if len(scored_matches) > 1 else -999
    is_confident = best_score >= 6 and (best_score - second_score >= 2)
    return best_project_id, candidate_ids, not is_confident


def _extract_epic(raw_text: str) -> str:
    for line in raw_text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        lower = line_clean.lower()
        if lower.startswith("эпик"):
            parts = re.split(r"[:\-]", line_clean, maxsplit=1)
            return parts[1].strip() if len(parts) > 1 else line_clean
    return ""


def _split_into_blocks(raw_text: str, projects: list[Project]) -> list[str]:
    lines = raw_text.splitlines()
    chunks: list[str] = []
    current_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip()
        if _starts_new_block(line, current_lines, projects):
            chunk = "\n".join(current_lines).strip()
            if chunk:
                chunks.append(chunk)
            current_lines = [line]
            continue
        current_lines.append(line)

    last_chunk = "\n".join(current_lines).strip()
    if last_chunk:
        chunks.append(last_chunk)

    if not chunks:
        return [raw_text.strip()] if raw_text.strip() else []
    return chunks


def _starts_new_block(line: str, current_lines: list[str], projects: list[Project]) -> bool:
    cleaned = line.strip()
    if not cleaned:
        return False
    if not current_lines:
        return False
    lowered = cleaned.lower()
    if lowered.startswith("дата:"):
        return True
    if lowered.startswith("эпик:") or lowered.startswith("проект:"):
        if _contains_only_metadata(current_lines):
            return False
        return True
    if _looks_like_project_heading(cleaned, projects):
        return True
    return False


def _looks_like_project_heading(cleaned: str, projects: list[Project]) -> bool:
    lowered = cleaned.lower()
    if len(cleaned) > 80:
        return False
    for project in projects:
        if project.name.lower() == "без проекта":
            continue
        if lowered == project.name.lower():
            return True
        for alias in project.aliases:
            alias_clean = alias.strip().lower()
            if alias_clean and lowered == alias_clean:
                return True
    return False


def _split_by_intent(raw_text: str) -> tuple[str, str, str, str]:
    structured = _split_structured_sections(raw_text)
    if structured is not None:
        return structured

    done_lines: list[str] = []
    plan_lines: list[str] = []
    risk_lines: list[str] = []
    for line in raw_text.splitlines():
        value = line.strip("-• \t")
        if not value:
            continue
        # Skip pure metadata lines (Проект:, Эпик:, Дата:, …).  They are
        # not bullet content and would otherwise leak into the draft as
        # "- Проект: Delivery." noise.
        if _is_metadata_line(value):
            continue
        lowered = value.lower()
        # Honor explicit section prefixes from structured notes / atomic split
        # FIRST so words like "проблеме" inside "Что сделано: … статус по проблеме …"
        # are not routed to risk via naive substring heuristics.
        if lowered.startswith(
            (
                "что сделано:",
                "что сделано -",
                "что сделано —",
                "сделано:",
            )
        ):
            done_lines.append(value)
            continue
        if lowered.startswith(("план:", "планы:", "план -", "план —")):
            plan_lines.append(value)
            continue
        if lowered.startswith(("риск:", "риски:", "риск -", "риск —")):
            risk_lines.append(value)
            continue
        if lowered.startswith(("блокер:", "блокеры:", "блокер -", "блокер —")):
            risk_lines.append(value)
            continue

        if any(token in lowered for token in ("план", "завтра", "дальше", "следующ", "next")):
            plan_lines.append(value)
            continue
        # Do not treat "проблема" alone as risk (explanatory "проблема в SDK…").
        if any(token in lowered for token in ("блокер", "завис", "пауз")):
            risk_lines.append(value)
            continue
        if _line_heuristic_suggests_risk(lowered):
            risk_lines.append(value)
            continue
        done_lines.append(value)
    if not done_lines and raw_text.strip() and not _is_metadata_line(raw_text.strip()):
        done_lines = [raw_text.strip()]
    return "", "\n".join(done_lines), "\n".join(plan_lines), "\n".join(risk_lines)


def _split_structured_sections(raw_text: str) -> tuple[str, str, str, str] | None:
    status_value = ""
    done_lines: list[str] = []
    plan_lines: list[str] = []
    risk_lines: list[str] = []
    loose_lines: list[str] = []
    current_section = ""
    saw_explicit_section = False

    for raw_line in raw_text.splitlines():
        value = raw_line.strip()
        if not value:
            continue

        heading = _match_section_heading(value)
        if heading is not None:
            saw_explicit_section = True
            section_name, inline_text = heading
            if section_name == "status":
                if inline_text:
                    status_value = inline_text
                current_section = ""
                continue
            if inline_text:
                _append_to_section(section_name, inline_text, done_lines, plan_lines, risk_lines)
                current_section = ""
            else:
                current_section = section_name
            continue

        if _is_metadata_line(value):
            continue

        if current_section:
            _append_to_section(current_section, value, done_lines, plan_lines, risk_lines)
            continue

        loose_lines.append(value)

    if not saw_explicit_section:
        return None

    if loose_lines:
        done_lines.extend(line for line in loose_lines if not _looks_like_report_heading(line))

    return status_value, "\n".join(done_lines), "\n".join(plan_lines), "\n".join(risk_lines)


def _match_section_heading(value: str) -> tuple[str, str] | None:
    normalized = value.strip("-• \t")
    lowered = normalized.lower()
    mapping = {
        "status": ("статус",),
        "done": ("что сделано", "что сделано сегодня", "сделано за сегодня"),
        "plan": (
            "план",
            "планы",
            "план на завтра",
            "планы на завтра",
            "планы на завтра/след неделю",
            "план / следующий шаг",
            "следующий шаг",
            "следующие шаги",
        ),
        "risk": ("риск", "риски", "риск / блокеры", "риски / блокеры", "риск/блокеры", "риски/блокеры", "блокеры"),
    }
    for section_name, prefixes in mapping.items():
        for prefix in prefixes:
            if lowered == prefix:
                return section_name, ""
            if lowered.startswith(f"{prefix}:") or lowered.startswith(f"{prefix} -"):
                parts = re.split(r"[:\-]", normalized, maxsplit=1)
                inline_text = parts[1].strip() if len(parts) > 1 else ""
                return section_name, inline_text
    return None


def _is_metadata_line(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith(("дата:", "менеджер:", "руководитель:", "проект:", "эпик:"))


def _line_heuristic_suggests_risk(lowered: str) -> bool:
    """Whether a non-heading line should be bucketed into risk by fuzzy match.

    Substring ``«риск»`` inside ``«риски»`` used to falsely fire on phrases like
    «риски оценены» (meta-summary, not a project risk).
    """
    if re.search(r"\bриски?\s+оценен\w*\b", lowered):
        return False
    return bool(re.search(r"\bриск[иа]?\b", lowered))


def _contains_only_metadata(lines: list[str]) -> bool:
    meaningful = [line.strip() for line in lines if line.strip()]
    if not meaningful:
        return True
    return all(_is_metadata_line(line) for line in meaningful)


def _looks_like_report_heading(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered.startswith("📝"):
        return True
    return bool(re.match(r"^\d+\.\s+", value))


def _append_to_section(
    section_name: str,
    value: str,
    done_lines: list[str],
    plan_lines: list[str],
    risk_lines: list[str],
) -> None:
    cleaned = value.strip("-• \t")
    if not cleaned:
        return
    if section_name == "done":
        done_lines.append(cleaned)
        return
    if section_name == "plan":
        plan_lines.append(cleaned)
        return
    if section_name == "risk":
        risk_lines.append(cleaned)
