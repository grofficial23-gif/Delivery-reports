"""Cleans report-item text before rendering.

Strips internal/synthetic prefixes that the parser injects ("вопрос —",
"блокер —", "решение —") AND user-typed leading labels ("Вопрос по
Bank Dashboard:", "Блокер по X:", "Проект: …") so that the user-facing
bullet contains only meaningful content.

Also provides *pre-clean* for whole messages pasted from assistants
(blockquote markdown, intro/meta lines, simple "Имя, привет." greetings).

This module is *pure*: no DB, no IO, no external services.  It is the
single source of truth for cleaning bullet text used by:
  • note_capture.render_saved_notes_message  (per-block bot reply)
  • draft_builder._render_bullets            (final daily draft)
  • report_presenter.build_note_preview      (dashboard previews)
  • parsing.parse_note_blocks / parse_note_text  (incoming raw text)
"""
from __future__ import annotations

import re


# Synthetic prefixes injected by parsing._atomic_to_block. Always lowercase.
# Order matters: longest first so we don't strip "решение" out of
# "решение —" before the dash is matched.
_SYNTHETIC_PREFIXES: tuple[str, ...] = (
    "решение —",
    "решение -",
    "вопрос —",
    "вопрос -",
    "блокер —",
    "блокер -",
    "риск —",
    "риск -",
    "план —",
    "план -",
)

# User-typed leading labels: "Блокер:", "Блокер по X:", "Решение по X:" etc.
# We strip up to and including the first ":" or "—" / "-" after the marker.
_USER_LEAD_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^\s*(?:блокер[ыа]?|риск[иа]?|план[ыа]?|вопрос|решение)\b"
        r"(?:\s+(?:по|на|в|о|для)\s+[^:—\-\n]{1,80})?"
        r"\s*[:\-—]\s*",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*что\s+сделано\s*[:\-—]\s*", re.IGNORECASE),
    re.compile(r"^\s*план\s+на\s+завтра\s*[:\-—]\s*", re.IGNORECASE),
    re.compile(r"^\s*следующий\s+шаг\s*[:\-—]\s*", re.IGNORECASE),
    # Project-switch prefixes that voice-dictated PMs use to change topic.
    # "Теперь по Bank Dashboard:", "Касательно Delivery Reports —",
    # "Дальше по DC701:" — we want only the content after the colon.
    re.compile(
        r"^\s*(?:теперь\s+по|переключаемся\s+(?:на|к)"
        r"|перейд[её]м\s+к|перехожу\s+к"
        r"|следующ(?:ий|ая)\s+(?:проект|тема)"
        r"|далее\s+по|дальше\s+по"
        r"|что\s+касается|касательно"
        r"|по\s+проекту|про\s+проект|по\s+теме)"
        r"\s+[^:—\-\n]{1,80}?"
        r"\s*[:\-—]\s*",
        re.IGNORECASE,
    ),
)

# A line that is JUST a project label — not real content.
_PROJECT_ONLY_LINE_RE = re.compile(
    r"^\s*проект\s*[:\-—]\s*[\w\-\s]{1,60}\s*\.?\s*$",
    re.IGNORECASE,
)

# Bullet leaders: -, •, *, "1.", "1)"
_BULLET_LEADER_RE = re.compile(r"^\s*(?:[-•*]|\d{1,2}[.)])\s+")

# Assistant/chat-meta lines (substring match, case-insensitive).
_ASSISTANT_META_SUBSTRINGS: tuple[str, ...] = (
    "вот готовый",
    "рабочий вариант сообщения",
    "можно отправить",
    "использовать как тезисы",
    "такой текст сразу показывает",
)

_GREETING_PREFIX_RE = re.compile(
    r"^\s*(?:[А-ЯЁ][а-яё\-]{1,40}|[A-Z][a-z\-]{1,40})\s*,\s*привет[.!]?\s*",
    re.UNICODE | re.IGNORECASE,
)


def pre_clean_incoming_report_text(text: str) -> str:
    """Remove assistant wrapper lines, markdown blockquotes/bold, and short greetings.

    Applied to full raw messages before block splitting / intent parsing so
    quoted Slack/Telegram markdown and ChatGPT intros do not land in drafts.
    Idempotent for typical inputs.
    """
    if not text or not text.strip():
        return text.strip() if text else ""
    out_lines: list[str] = []
    for raw in text.splitlines():
        work = raw.strip("\r")
        if not work.strip():
            continue
        # Peel Markdown blockquote and nested list markers (repeat).
        for _ in range(6):
            before = work
            work = re.sub(r"^\s*>\s?", "", work, count=1)
            work = re.sub(r"^\s*[*•\-]+\s+", "", work, count=1)
            if work == before:
                break
        work = work.replace("**", "").strip()
        if not work:
            continue
        row = work.lower()
        if any(sub in row for sub in _ASSISTANT_META_SUBSTRINGS):
            continue
        work = _GREETING_PREFIX_RE.sub("", work, count=1).strip()
        if not work:
            continue
        out_lines.append(work)
    return "\n".join(out_lines)


def clean_report_item_text(
    text: str,
    *,
    project_name: str | None = None,
    intent_kind: str | None = None,
) -> str:
    """Return a cleaned, user-facing version of *text*.

    Returns an empty string when the input is empty, whitespace-only,
    or consists solely of a project label ("Проект: Delivery.").

    Multiple synthetic/user prefixes may stack ("решение — Решение по X: …");
    we strip them iteratively until the text is stable.
    """
    if not text:
        return ""
    cleaned = text.strip()
    if not cleaned:
        return ""

    cleaned = _BULLET_LEADER_RE.sub("", cleaned).strip()
    if not cleaned:
        return ""

    if _PROJECT_ONLY_LINE_RE.match(cleaned):
        return ""

    # Iteratively peel off synthetic + user prefixes (they can stack).
    for _ in range(8):
        before = cleaned
        lowered = cleaned.lower()
        stripped_synthetic = False
        for prefix in _SYNTHETIC_PREFIXES:
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix):].lstrip(" \t-—:")
                stripped_synthetic = True
                break
        if stripped_synthetic:
            continue
        new_cleaned = cleaned
        for pattern in _USER_LEAD_RES:
            new_cleaned = pattern.sub("", new_cleaned, count=1)
        if new_cleaned != cleaned:
            cleaned = new_cleaned
            continue
        if cleaned == before:
            break

    cleaned = cleaned.strip(" \t-—:.")
    if not cleaned:
        return ""

    if _PROJECT_ONLY_LINE_RE.match(cleaned):
        return ""

    return _capitalize_first(cleaned)


def _capitalize_first(text: str) -> str:
    if not text:
        return text
    first = text[0]
    if first.isalpha() and first.islower():
        return first.upper() + text[1:]
    return text
