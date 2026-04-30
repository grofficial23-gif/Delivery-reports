"""Preprocess raw chat/status dumps before LLM extraction."""

from __future__ import annotations

import os
import re
import unicodedata


_SECTION_HEADERS = frozenset(
    {
        "что сделано",
        "сделано",
        "done",
        "plan",
        "планы",
        "риски",
        "risks",
        "блокеры",
        "blockers",
        "в работе",
        "in progress",
        "готово",
        "on merge",
        "завершено",
        "pause",
        "на паузе",
        "решения",
        "decisions",
    }
)

_RE_TIME_BRACKET = re.compile(r"^\s*\[\s*\d{1,2}:\d{2}\s*\]\s*")
_RE_PREFIX_NICK = re.compile(r"^\s*([^\s:]{1,24}):\s*", re.UNICODE)

# Do not treat structured report labels as chat nicks
_NICK_DENY = frozenset(
    {
        "риск",
        "риски",
        "план",
        "планы",
        "блокер",
        "блокеры",
        "что сделано",
        "сделано",
        "done",
        "status",
        "статус",
    }
)
# Line starting with > or >>
_RE_QUOTE = re.compile(r"^\s*>{1,2}\s?")


def _has_letter_or_digit(line: str) -> bool:
    for ch in line:
        if ch.isdigit():
            return True
        cat = unicodedata.category(ch)
        if cat.startswith("L"):
            return True
    return False


def _is_emoji_or_symbol_only_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    return not _has_letter_or_digit(s)


def _strip_section_header(line: str) -> str:
    key = line.strip().lower().rstrip(":")
    if key in _SECTION_HEADERS:
        return ""
    return line


def preprocess(raw: str) -> str:
    """Normalize chat dumps; return original if cleanup would be too aggressive."""
    if not raw:
        return raw
    max_chars = int(os.getenv("CHAT_DUMP_MAX_INPUT_CHARS", "8000"))
    original = raw

    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    for line in lines:
        line = _RE_QUOTE.sub("", line)
        line = _strip_section_header(line)
        if not line.strip():
            out.append("")
            continue
        if _is_emoji_or_symbol_only_line(line):
            continue
        line = _RE_TIME_BRACKET.sub("", line)
        m = _RE_PREFIX_NICK.match(line)
        if m:
            nick = m.group(1).strip().lower()
            if nick not in _NICK_DENY:
                line = line[m.end() :]
        line = line.strip()
        if _is_emoji_or_symbol_only_line(line):
            continue
        line = _strip_section_header(line)
        if line.strip():
            out.append(line.strip())
        else:
            out.append("")

    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) < 10:
        text = original.strip()
    if len(text) > max_chars:
        text = text[:max_chars]
    return text
