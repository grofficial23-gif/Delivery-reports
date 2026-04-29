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


# ── Intent classification rules ────────────────────────────────────────
# Strict-by-default. Neutral mentions of words like "блокер" or "сделано"
# inside a free-form sentence MUST NOT trigger that intent. We only fire
# on:
#   1. Strong sentence-start markers ("Блокер: …", "Риск по …", "План на …")
#   2. Strong verb phrases (anywhere, word-boundary aware)
#   3. Trailing "?" for question.
#
# Order of resolution (most specific wins):
#   blocker → decision → risk → question → plan → done → other.

# Strong start-of-sentence patterns. The marker must be followed by
# ":" / "-" / "—" (label punctuation) OR by " по "/" на "/" в "/" о "
# (preposition that introduces a project / topic / object).
_STRONG_START_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("blocker", re.compile(r"^\s*блокер[ыа]?\b\s*[:\-—]", re.IGNORECASE)),
    ("blocker", re.compile(r"^\s*блокер[ыа]?\b\s+(?:по|на|в|о|для)\b", re.IGNORECASE)),
    ("decision", re.compile(r"^\s*решение\b\s*[:\-—]", re.IGNORECASE)),
    ("decision", re.compile(r"^\s*решение\b\s+(?:по|на|в|о)\b", re.IGNORECASE)),
    ("decision", re.compile(r"^\s*решили\b", re.IGNORECASE)),
    ("decision", re.compile(r"^\s*приняли\s+решение\b", re.IGNORECASE)),
    ("risk", re.compile(r"^\s*риск[иа]?\b\s*[:\-—]", re.IGNORECASE)),
    ("risk", re.compile(r"^\s*риск[иа]?\b\s+(?:по|на|в|о|для)\b", re.IGNORECASE)),
    ("question", re.compile(r"^\s*вопрос\b\s*[:\-—]", re.IGNORECASE)),
    ("question", re.compile(r"^\s*вопрос\b\s+(?:по|на|в|о)\b", re.IGNORECASE)),
    ("plan", re.compile(r"^\s*план[ыа]?\b\s*[:\-—]", re.IGNORECASE)),
    ("plan", re.compile(r"^\s*план[ыа]?\b\s+(?:на|по|для)\b", re.IGNORECASE)),
    # "Завтра делаем демо" / "Завтра подписываем акты" — clear future intent.
    ("plan", re.compile(r"^\s*(?:завтра|послезавтра|на\s+след(?:ующ\w+)?)\b", re.IGNORECASE)),
)

# Anywhere-in-sentence markers, matched as full words (Unicode-aware).
# Each entry: (intent, pattern). Order checked in priority sequence.
_STRONG_BLOCKER_PATTERNS: tuple["re.Pattern[str]", ...] = (
    re.compile(r"^\s*нет\s+доступа\b", re.IGNORECASE),
    re.compile(r"\bзаблокирован[оы]?\b", re.IGNORECASE),
    re.compile(r"\bне\s+можем\s+продолжить\b", re.IGNORECASE),
    re.compile(r"\bне\s+пуска[е]?т\b", re.IGNORECASE),
    re.compile(r"\bблокирует\b", re.IGNORECASE),
)

_STRONG_RISK_PATTERNS: tuple["re.Pattern[str]", ...] = (
    re.compile(r"\bесть\s+риск\b", re.IGNORECASE),
    re.compile(r"\bпод\s+вопросом\b", re.IGNORECASE),
    re.compile(r"\bопасн(?:о|ость)\b", re.IGNORECASE),
    re.compile(r"\bможет\s+(?:слететь|уехать|сорваться|задержаться)\b", re.IGNORECASE),
    re.compile(r"\bне\s+уверен\s+в\s+сроках\b", re.IGNORECASE),
    re.compile(r"\bможет\s+закэшировать\b", re.IGNORECASE),
    re.compile(r"\bможем\s+не\s+успеть\b", re.IGNORECASE),
)

_STRONG_PLAN_PATTERNS: tuple["re.Pattern[str]", ...] = (
    re.compile(r"\bбуд(?:у|ем|ут)\s+делать\b", re.IGNORECASE),
    re.compile(r"\bпланиру[ею]т?\b", re.IGNORECASE),
    re.compile(r"\bзапланир\w+\b", re.IGNORECASE),
    re.compile(r"\bнадо\s+сделать\b", re.IGNORECASE),
    re.compile(r"\bнужно\s+сделать\b", re.IGNORECASE),
    re.compile(r"\bхочу\s+сделать\b", re.IGNORECASE),
    re.compile(r"\bна\s+завтра\b", re.IGNORECASE),
    re.compile(r"\bна\s+след\w+\b", re.IGNORECASE),
    re.compile(r"\bдоделать\b", re.IGNORECASE),
    re.compile(r"\bnext\s+(?:week|sprint)\b", re.IGNORECASE),
)

_STRONG_DECISION_PATTERNS: tuple["re.Pattern[str]", ...] = (
    re.compile(r"\bприняли\s+решение\b", re.IGNORECASE),
    re.compile(r"\bдоговорились\b", re.IGNORECASE),
    re.compile(r"\bутвердили\b", re.IGNORECASE),
    re.compile(r"^\s*решили\b", re.IGNORECASE),
    re.compile(r"\bрешили\s+не\b", re.IGNORECASE),
    re.compile(r"\bне\s+будем\b", re.IGNORECASE),
    re.compile(r"\bчтобы\s+не\s+сломать\b", re.IGNORECASE),
    re.compile(r"\bможем\s+сломать\b", re.IGNORECASE),
)

# Done verbs — word-boundary, anywhere. These are unambiguous past-tense
# completion verbs.
_STRONG_DONE_PATTERNS: tuple["re.Pattern[str]", ...] = (
    re.compile(
        r"\b("
        r"сделал[аи]?|сделано"
        r"|закрыл[аи]?|выкатил[аи]?|выпустил[аи]?|запустил[аи]?"
        r"|релизнул[аи]?|внедрил[аи]?|доделал[аи]?|оформил[аи]?"
        r"|завершил[аи]?|закрыли|проверил[аи]?|выяснили"
        r"|подписал[аи]?|обсудил[аи]?|согласовал[аи]?"
        r"|поправил[аи]?|добавил[аи]?|починил[аи]?|настроил[аи]?"
        r"|протестировал[аи]?|провел[аи]?|провёл"
        r"|deployed|merged|shipped|ready"
        r")\b",
        re.IGNORECASE,
    ),
)

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
        explicit_hint = _extract_explicit_project(cleaned, project_list)
        alias_hint = _detect_project_by_alias(cleaned, project_list)
        hint = explicit_hint or alias_hint
        switch = _is_project_switch(cleaned)
        # A pure project-introduction sentence ("Проект: X", "По X")
        # only sets the carry-over hint. It MUST NOT become a bullet
        # because it has no real content.
        if _is_project_only_sentence(cleaned, project_list):
            if hint:
                last_project = hint
            elif switch:
                last_project = ""
            continue
        if hint:
            last_project = hint
        elif switch:
            # User explicitly switched topic but didn't name the project yet.
            last_project = ""
        intent = _classify_intent(cleaned)
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
    #
    # Important: ONLY merge {done, plan, other} items.  Blockers, risks,
    # decisions and questions deserve dedicated bullets so the reader sees
    # each one distinctly — merging two blockers into "Block A. Block B."
    # would be a UX regression.
    _MERGEABLE = {"done", "plan", "other"}
    merged: list[AtomicUpdate] = []
    for atom in raw_atoms:
        if (
            merged
            and atom.intent in _MERGEABLE
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
    """Classify a single sentence into a coarse intent.

    Strict rules — neutral mentions of "блокер" / "сделано" / "риск" inside a
    free-form sentence MUST NOT trigger that intent. We only fire on:
      1. Strong sentence-start markers (regex anchored at start).
      2. Strong full-word verb patterns anywhere (word-boundary aware).
      3. Trailing "?" for question.

    Order: blocker → decision → risk → question → plan → done → other.
    """
    cleaned = sentence.strip()
    if not cleaned:
        return "other"

    for intent_kind, pattern in _STRONG_START_PATTERNS:
        if pattern.search(cleaned):
            return intent_kind

    for pattern in _STRONG_BLOCKER_PATTERNS:
        if pattern.search(cleaned):
            return "blocker"

    for pattern in _STRONG_DECISION_PATTERNS:
        if pattern.search(cleaned):
            return "decision"

    for pattern in _STRONG_RISK_PATTERNS:
        if pattern.search(cleaned):
            return "risk"

    if cleaned.endswith("?"):
        return "question"

    for pattern in _STRONG_PLAN_PATTERNS:
        if pattern.search(cleaned):
            return "plan"

    for pattern in _STRONG_DONE_PATTERNS:
        if pattern.search(cleaned):
            return "done"

    return "other"


# Sentences whose entire content is a project introduction
# ("Проект: X", "По проекту X", "По <alias>") must NOT become bullets in
# the report — they only set the project hint.
_PROJECT_LABEL_RES: tuple["re.Pattern[str]", ...] = (
    re.compile(r"^\s*проект\s*[:\-—]\s*(.+)$", re.IGNORECASE),
    re.compile(r"^\s*(?:по\s+проекту|касательно)\s+(.+)$", re.IGNORECASE),
)


def _is_project_only_sentence(sentence: str, projects: list[Project]) -> bool:
    """True if the sentence is JUST a project label / introduction.

    Examples:
      "Проект: Delivery."                       → True
      "По проекту DC701"                         → True
      "По проекту DC701 закрыли миграцию"        → False (has real content)
      "По цод закрыли освобождение."             → False (has real content)
    """
    cleaned = sentence.strip().rstrip(".:!?")
    if not cleaned:
        return True
    # "Проект: X" / "По проекту X" / "Касательно X" — drop only when the
    # candidate is JUST a project reference (matches a known name/alias)
    # OR is a single short token (≤ 3 words, ≤ 40 chars).
    for pattern in _PROJECT_LABEL_RES:
        match = pattern.match(cleaned)
        if not match:
            continue
        candidate = match.group(1).strip().rstrip(".:!?").strip()
        if not candidate:
            return True
        if _resolve_to_known_name(candidate, projects):
            return True
        # No verbs / connectives → likely just a project label.
        if len(candidate.split()) <= 3 and len(candidate) <= 40 and not _has_action_word(candidate):
            return True
    # "По <known-project-name-or-alias>" alone.
    lowered = cleaned.lower()
    if lowered.startswith("по "):
        candidate = cleaned[3:].strip().rstrip(".:!?")
        if candidate and _resolve_to_known_name(candidate, projects):
            return True
    return False


_ACTION_WORD_RE = re.compile(
    r"\b("
    r"сделал[аи]?|закрыл[аи]?|выкатил[аи]?|релизнул[аи]?|внедрил[аи]?"
    r"|доделал[аи]?|оформил[аи]?|завершил[аи]?|подписал[аи]?"
    r"|обсудил[аи]?|согласовал[аи]?|поправил[аи]?|добавил[аи]?"
    r"|настроил[аи]?|починил[аи]?|провел[аи]?|провёл"
    r"|планир\w+|запланир\w+|буд[уе]м?\s+делать"
    r"|есть|был[аи]?|будет|сделано"
    r"|releas\w*|deploy\w*|merg\w*|ship\w*|migrat\w*"
    r")\b",
    re.IGNORECASE,
)


def _has_action_word(text: str) -> bool:
    return bool(_ACTION_WORD_RE.search(text))


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
    """Match the most likely project name using project name + aliases.

    Rules:
      - Case-insensitive.
      - Word-boundary matching (Unicode-aware).
      - Single-word aliases only count when length >= 3 to avoid false
        positives on common short tokens ("ID", "QA", "RU").
      - Multi-word phrase aliases ("Bank Dashboard") score before
        single-word aliases ("Bank") to prefer the more specific match.
      - Highest score wins; ties broken by phrase length (longer wins).
    """
    lowered = sentence.lower()
    best_name = ""
    best_score = 0
    best_specificity = 0  # length of the longest matched token
    for project in projects:
        name = (project.name or "").strip()
        if not name or name.lower() == "без проекта":
            continue
        score = 0
        specificity = 0
        name_lower = name.lower()
        if _word_in_text(name_lower, lowered):
            # Phrase-name match is the strongest signal. Bonus for phrases.
            phrase_bonus = 4 if " " in name_lower else 0
            score += max(2, len(name_lower)) + phrase_bonus
            specificity = max(specificity, len(name_lower))
        # Sort aliases: phrase (multi-word) first, then by length desc.
        aliases_sorted = sorted(
            ((a or "").strip().lower() for a in (project.aliases or ())),
            key=lambda a: (-(1 if " " in a else 0), -len(a)),
        )
        for alias_clean in aliases_sorted:
            if not alias_clean:
                continue
            # Skip dangerously short single-word aliases.
            if " " not in alias_clean and len(alias_clean) < 3:
                continue
            if _word_in_text(alias_clean, lowered):
                phrase_bonus = 3 if " " in alias_clean else 0
                score += max(1, len(alias_clean)) + phrase_bonus
                specificity = max(specificity, len(alias_clean))
        if score > best_score or (score == best_score and specificity > best_specificity):
            best_score = score
            best_specificity = specificity
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
