from __future__ import annotations

from html import unescape
import re

from ..repository import Note


_A_TAG_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_MARKER_SPLIT_RE = re.compile(
    r"(?=(?:статус|действие|результат|риск|риски|блокер|блокеры|дедлайн|срок|следующий шаг|план)\s*:)",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+(?=[A-ZА-Я0-9@])")


def compact_section_items(items: list[str], section: str, max_chars: int = 220) -> list[str]:
    seen: set[str] = set()
    compacted: list[str] = []
    for item in items:
        for chunk in _explode_dense_item(item, max_chars=max_chars):
            normalized = " ".join(chunk.split())
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            compacted.append(normalized)
    return compacted


def limit_section_items(items: list[str], section: str, style: str) -> list[str]:
    # Per-style per-section caps. Sections not listed are unlimited.
    # concise = "Только главное" — strict 2-3 bullets per section.
    concise_limits = {
        "done": 2, "plan": 1, "risk": 1, "blocker": 1,
        "decision": 1, "question": 1,
    }
    standard_limits = {"done": 6, "plan": 4, "risk": 3, "blocker": 3}
    active_limits = concise_limits if style == "concise" else standard_limits
    limit = active_limits.get(section, len(items))
    if len(items) <= limit:
        return items
    hidden_count = len(items) - limit
    return [*items[:limit], f"… ещё {hidden_count} пункт(а)"]


def build_note_preview(note: Note, max_chars: int = 420) -> str:
    lines: list[str] = []
    if note.status_text.strip():
        lines.append(f"Статус: {_shorten(note.status_text.strip(), 90)}")

    done_items = summarize_block(note.done_text, max_items=2)
    plan_items = summarize_block(note.plan_text, max_items=2)
    risk_items = summarize_block(note.risk_text, max_items=1)

    if done_items:
        lines.append(f"Сделано: {' | '.join(done_items)}")
    if plan_items:
        lines.append(f"Дальше: {' | '.join(plan_items)}")
    if risk_items:
        lines.append(f"Блокеры: {' | '.join(risk_items)}")

    if not lines:
        fallback = " ".join(note.raw_text.split())
        return _shorten(fallback, max_chars)
    return _shorten("\n".join(lines), max_chars)


def summarize_block(block_text: str, max_items: int = 2, max_chars: int = 120) -> list[str]:
    raw_items = [line.strip("-• \t") for line in block_text.splitlines() if line.strip()]
    compacted = compact_section_items(raw_items, section="preview", max_chars=max_chars)
    return [_shorten(item, max_chars) for item in compacted[:max_items]]


def html_report_to_plain_text(content: str) -> str:
    if not content.strip():
        return ""

    text = _A_TAG_RE.sub(_replace_link, content)
    replacements = {
        "<br>": "\n",
        "<br/>": "\n",
        "<br />": "\n",
        "</p>": "\n\n",
        "</div>": "\n",
        "</li>": "\n",
        "<li>": "- ",
        "</ul>": "\n",
        "</ol>": "\n",
        "</pre>": "\n",
        "</code>": "",
        "<code>": "",
        "<pre>": "",
        "<b>": "",
        "</b>": "",
        "<strong>": "",
        "</strong>": "",
        "<i>": "",
        "</i>": "",
        "<em>": "",
        "</em>": "",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    text = _TAG_RE.sub("", text)
    text = unescape(text)
    lines = [line.rstrip() for line in text.splitlines()]

    compact_lines: list[str] = []
    blank_streak = 0
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            blank_streak += 1
            if blank_streak <= 1:
                compact_lines.append("")
            continue
        blank_streak = 0
        compact_lines.append(" ".join(cleaned.split()))

    return "\n".join(compact_lines).strip()


def split_telegram_chunks(text: str, max_length: int = 3900) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    if len(normalized) <= max_length:
        return [normalized]

    chunks: list[str] = []
    remaining = normalized
    while len(remaining) > max_length:
        split_at = remaining.rfind("\n\n", 0, max_length)
        if split_at < max_length * 0.55:
            split_at = remaining.rfind("\n", 0, max_length)
        if split_at < max_length * 0.55:
            split_at = remaining.rfind(" ", 0, max_length)
        if split_at <= 0:
            split_at = max_length
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _explode_dense_item(item: str, max_chars: int) -> list[str]:
    normalized = " ".join(item.split())
    if not normalized:
        return []

    marker_parts = [part.strip(" -") for part in _MARKER_SPLIT_RE.split(normalized) if part.strip(" -")]
    candidates = marker_parts if len(marker_parts) > 1 else [normalized]

    exploded: list[str] = []
    for candidate in candidates:
        if len(candidate) > max_chars:
            sentence_parts = [part.strip(" -") for part in _SENTENCE_SPLIT_RE.split(candidate) if part.strip(" -")]
            if len(sentence_parts) > 1:
                exploded.extend(_shorten(part, max_chars) for part in sentence_parts)
                continue
        exploded.append(_shorten(candidate, max_chars))
    return exploded


def _replace_link(match: re.Match[str]) -> str:
    href = unescape(match.group(1))
    label = _TAG_RE.sub("", match.group(2)).strip() or href
    return f"{label} ({href})"


def _shorten(text: str, max_chars: int) -> str:
    value = " ".join(text.split())
    if len(value) <= max_chars:
        return value
    clipped = value[: max_chars + 1]
    boundary = clipped.rfind(" ")
    if boundary >= max_chars * 0.6:
        clipped = clipped[:boundary]
    else:
        clipped = clipped[:max_chars]
    return clipped.rstrip(" ,;:-") + "..."
