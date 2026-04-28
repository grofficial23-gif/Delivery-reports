"""Heuristic splitter for long unstructured PM updates (e.g. dictated voice).

Goal: turn a 5-60 minute monolog into a list of *atomic* update items, each
tagged with a coarse intent (done / plan / risk / blocker / decision /
question / other) and an optional project-name hint.

This module is *pure*: no DB, no IO, no external AI. It is safe to call from
parsing.py and from tests directly.

Design notes
------------
- We never *drop* text. Every non-empty sentence ends up in some atom.
- We bias toward *fewer* atoms (merge consecutive same-intent + same-project
  items) to avoid dashboard noise.
- Project hint is best-effort; resolution still happens downstream via the
  existing project_resolution pipeline.
- Russian-first vocabulary, with a few common English markers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable

from ..repository import Project


VALID_INTENTS = ("done", "plan", "risk", "blocker", "decision", "question", "other")


@dataclass(frozen=True)
class AtomicUpdate:
    text: str
    intent: str  # one of VALID_INTENTS
    project_name_hint: str = ""


# ── Intent vocabularies ────────────────────────────────────────────────
# All entries must be lowercase. Substring match against the lowered sentence.
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Order matters: more specific intents (blocker, decision, risk) are
    # checked before generic done/plan.
    "blocker": (
        "блокер", "заблокирован", "застрял", "застряли", "зависли",
        "ждём", "ждем", "ожидаем", "висит на стороне",
        "не можем", "не получается", "не пускают", "stuck", "blocked",
    ),
    "decision": (
        "решили", "приняли решение", "договорились", "утвердили",
        "согласовали", "decision", "agreed",
    ),
    "risk": (
        "риск", "риски", "может слететь", "может уехать", "может сорваться",
        "под вопросом", "опасн", "не уверен в сроках", "грозит",
        "вероятно сорв", "risk",
    ),
    "plan": (
        "завтра", "планир", "план на", "буду делать", "будем делать",
        "надо сделать", "нужно сделать", "запланир",
        "на след", "next week", "next sprint", "потом сделаем",
        "to do", "todo", "хочу сделать",
    ),
    "done": (
        "сделал", "сделали", "сделано", "закрыл", "закрыли",
        "релиз", "выкатил", "выкатили", "выпустили", "запустили",
        "подписали", "провели", "протестировал", "внедрил", "внедрили",
        "доделал", "доделали", "оформили", "отправил", "отправили",
        "завершил", "завершили", "deployed", "merged", "shipped",
        "ready", "demo прошл", "демо прошл",
    ),
}

# Phrases that signal a project switch — drop carry-over.
_PROJECT_SWITCH_MARKERS = (
    "теперь по",
    "переключаемся",
    "перейдём к",
    "перейдем к",
    "перехожу к",
    "другой проект",
    "по другому проекту",
    "следующий проект",
    "следующая тема",
    "далее по",
    "дальше по",
    "что касается",
    "касательно",
    "по проекту",
    "по теме",
)

# Markers that introduce a project name explicitly: "по проекту X", "касательно X"
_PROJECT_INTRO_RE = re.compile(
    r"(?:по\s+проекту|касательно|про\s+проект|по\s+теме)\s+([A-Za-zА-Яа-я0-9_\-\.]{2,40})",
    re.IGNORECASE,
)

# Sentence boundary: . ! ? … followed by space or EOL; also newlines, " — ", "; ".
# We keep the boundary punctuation with the preceding sentence.
_SENT_SPLIT_RE = re.compile(
    r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ0-9«\"\(])"
    r"|(?:\r?\n)+"
    r"|\s—\s"
    r"|;\s+",
)

# Bullet markers at the start of a line: -, •, *, 1., 1)
_BULLET_RE = re.compile(r"^\s*(?:[-•*]|\d{1,2}[.)])\s+")

_MIN_LONG_LEN = 200  # chars threshold for "long" unstructured text
_MIN_LONG_SENTENCES = 3


def looks_long_unstructured(raw_text: str) -> bool:
    """Decide if the input is worth running through the heuristic splitter.

    Short notes (< 200 chars and < 3 sentences) keep the original behavior.
    """
    text = (raw_text or "").strip()
    if not text:
        return False
    if len(text) >= _MIN_LONG_LEN:
        return True
    return len(_split_into_sentences(text)) >= _MIN_LONG_SENTENCES


def split_long_update(
    raw_text: str,
    projects: list[Project] | Iterable[Project],
) -> list[AtomicUpdate]:
    """Split a long unstructured update into atomic items.

    Returns at least one item if input is non-empty. Never raises on bad input.
    """
    text = (raw_text or "").strip()
    if not text:
        return []

    project_list = list(projects) if projects is not None else []
    sentences = _split_into_sentences(text)
    if not sentences:
        return [AtomicUpdate(text=text, intent="other")]

    # Step 1: classify each sentence, detect project hint per sentence.
    raw_atoms: list[AtomicUpdate] = []
    last_project = ""
    for sentence in sentences:
        cleaned = _clean_bullet(sentence).strip()
        if not cleaned:
            continue
        intent = _classify_intent(cleaned)
        switch = _is_project_switch(cleaned)
        explicit_hint = _extract_explicit_project(cleaned, project_list)
        alias_hint = _detect_project_by_alias(cleaned, project_list)
        hint = explicit_hint or alias_hint
        if hint:
            last_project = hint
        elif switch:
            # User explicitly switched topic but didn't name the project yet.
            last_project = ""
        # Carry-over: if no hint here and not a switch, inherit from previous.
        effective_hint = hint or (last_project if not switch else "")
        raw_atoms.append(
            AtomicUpdate(
                text=cleaned,
                intent=intent,
                project_name_hint=effective_hint,
            )
        )

    if not raw_atoms:
        return [AtomicUpdate(text=text, intent="other")]

    # Step 2: merge adjacent atoms with the same (intent, project_hint) and
    # short combined length to keep the report tidy.
    merged: list[AtomicUpdate] = []
    for atom in raw_atoms:
        if (
            merged
            and merged[-1].intent == atom.intent
            and merged[-1].project_name_hint == atom.project_name_hint
            and len(merged[-1].text) + len(atom.text) <= 220
        ):
            prev = merged[-1]
            merged[-1] = AtomicUpdate(
                text=_join_two(prev.text, atom.text),
                intent=prev.intent,
                project_name_hint=prev.project_name_hint,
            )
        else:
            merged.append(atom)
    return merged


# ── Internals ──────────────────────────────────────────────────────────


def _split_into_sentences(text: str) -> list[str]:
    # Split first by newlines to honor explicit bullet lines, then by punctuation.
    out: list[str] = []
    for line in (raw.strip() for raw in text.splitlines()):
        if not line:
            continue
        chunks = _SENT_SPLIT_RE.split(line)
        for chunk in chunks:
            cleaned = chunk.strip()
            if cleaned:
                out.append(cleaned)
    return out


def _clean_bullet(sentence: str) -> str:
    return _BULLET_RE.sub("", sentence)


def _classify_intent(sentence: str) -> str:
    lowered = sentence.lower()
    if lowered.endswith("?") or "вопрос" in lowered or "уточнить" in lowered:
        return "question"
    for intent in ("blocker", "decision", "risk", "plan", "done"):
        for token in _INTENT_KEYWORDS[intent]:
            if token in lowered:
                return intent
    return "other"


def _is_project_switch(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(marker in lowered for marker in _PROJECT_SWITCH_MARKERS)


def _extract_explicit_project(sentence: str, projects: list[Project]) -> str:
    match = _PROJECT_INTRO_RE.search(sentence)
    if not match:
        return ""
    candidate = match.group(1).strip(" ,.;:")
    if not candidate:
        return ""
    # Prefer canonical project name if the candidate matches a known alias.
    resolved = _resolve_to_known_name(candidate, projects)
    return resolved or candidate


def _detect_project_by_alias(sentence: str, projects: list[Project]) -> str:
    lowered = sentence.lower()
    best_name = ""
    best_score = 0
    for project in projects:
        name = (project.name or "").strip()
        if not name or name.lower() == "без проекта":
            continue
        score = 0
        name_lower = name.lower()
        if _word_in_text(name_lower, lowered):
            score += max(2, len(name_lower))
        for alias in project.aliases or ():
            alias_clean = (alias or "").strip().lower()
            if not alias_clean:
                continue
            if _word_in_text(alias_clean, lowered):
                score += max(1, len(alias_clean))
        if score > best_score:
            best_score = score
            best_name = name
    return best_name if best_score > 0 else ""


def _resolve_to_known_name(candidate: str, projects: list[Project]) -> str:
    cand_lower = candidate.lower()
    for project in projects:
        if (project.name or "").lower() == cand_lower:
            return project.name
        for alias in project.aliases or ():
            if (alias or "").strip().lower() == cand_lower:
                return project.name
    return ""


def _word_in_text(needle: str, haystack: str) -> bool:
    """Word-ish containment check tolerant to RU/EN identifiers.

    Avoids matching "co" inside "score" by anchoring on word boundaries
    when the needle is alphanumeric.
    """
    if not needle:
        return False
    if not re.search(r"\w", needle):
        return needle in haystack
    pattern = r"(?<!\w)" + re.escape(needle) + r"(?!\w)"
    return re.search(pattern, haystack, flags=re.IGNORECASE) is not None


def _join_two(a: str, b: str) -> str:
    a = a.rstrip()
    b = b.lstrip()
    if not a:
        return b
    if a.endswith((".", "!", "?", "…", ":", ";", ",")):
        return f"{a} {b}"
    return f"{a}. {b}"
