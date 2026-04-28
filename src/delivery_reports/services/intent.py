"""Intent labels + safe inference from existing note fields.

Used by the V2 dashboard to render intent badges on note cards and by
note_capture to summarize how a long monologue was auto-split.

Pure module: no DB, no IO, no schema change. The inference reads the
already-stored note fields (`done_text`, `plan_text`, `risk_text`,
`needs_review`) plus the prefix annotations injected by
`parse_note_blocks` for atomic blocks ("решение —", "вопрос —",
"блокер —"). When in doubt we degrade gracefully to "other".
"""
from __future__ import annotations

from dataclasses import dataclass


INTENT_KIND_DONE = "done"
INTENT_KIND_PLAN = "plan"
INTENT_KIND_RISK = "risk"
INTENT_KIND_BLOCKER = "blocker"
INTENT_KIND_DECISION = "decision"
INTENT_KIND_QUESTION = "question"
INTENT_KIND_OTHER = "other"

VALID_INTENT_KINDS: tuple[str, ...] = (
    INTENT_KIND_DONE,
    INTENT_KIND_PLAN,
    INTENT_KIND_RISK,
    INTENT_KIND_BLOCKER,
    INTENT_KIND_DECISION,
    INTENT_KIND_QUESTION,
    INTENT_KIND_OTHER,
)

INTENT_LABELS: dict[str, str] = {
    INTENT_KIND_DONE: "✓ Сделано",
    INTENT_KIND_PLAN: "→ План",
    INTENT_KIND_RISK: "⚠ Риск",
    INTENT_KIND_BLOCKER: "⛔ Блокер",
    INTENT_KIND_DECISION: "◆ Решение",
    INTENT_KIND_QUESTION: "? Вопрос",
    INTENT_KIND_OTHER: "• Апдейт",
}

# Plural forms for "auto-split" summary line.
INTENT_PLURAL_LABELS: dict[str, str] = {
    INTENT_KIND_DONE: "сделано",
    INTENT_KIND_PLAN: "плана",
    INTENT_KIND_RISK: "риск",
    INTENT_KIND_BLOCKER: "блокер",
    INTENT_KIND_DECISION: "решение",
    INTENT_KIND_QUESTION: "вопрос",
    INTENT_KIND_OTHER: "апдейт",
}


@dataclass(frozen=True)
class _Fields:
    done_text: str
    plan_text: str
    risk_text: str
    needs_review: bool


def label_for_kind(kind: str) -> str:
    return INTENT_LABELS.get(kind, INTENT_LABELS[INTENT_KIND_OTHER])


def infer_intent_kind(
    *,
    done_text: str = "",
    plan_text: str = "",
    risk_text: str = "",
    needs_review: bool = False,
) -> str:
    """Infer a single coarse intent for a stored note.

    Order of precedence (most specific wins):
        1. blocker  — risk text begins with "блокер" / has "block" markers,
                      or needs_review with risk content
        2. risk     — non-empty risk_text without blocker prefix
        3. decision — done_text begins with "решение —"
        4. question — done_text begins with "вопрос —"
        5. plan     — non-empty plan_text
        6. done     — non-empty done_text
        7. other    — everything else (e.g. status_text only, or empty)
    """
    fields = _Fields(
        done_text=(done_text or "").strip(),
        plan_text=(plan_text or "").strip(),
        risk_text=(risk_text or "").strip(),
        needs_review=bool(needs_review),
    )
    risk_lower = fields.risk_text.lower()
    if fields.risk_text and (
        risk_lower.startswith("блокер")
        or "блокер —" in risk_lower
        or "блокер -" in risk_lower
    ):
        return INTENT_KIND_BLOCKER
    if fields.risk_text and not _is_empty_risk_marker(fields.risk_text):
        return INTENT_KIND_RISK

    done_lower = fields.done_text.lower()
    if done_lower.startswith("решение —") or done_lower.startswith("решение -"):
        return INTENT_KIND_DECISION
    if done_lower.startswith("вопрос —") or done_lower.startswith("вопрос -"):
        return INTENT_KIND_QUESTION

    if fields.plan_text:
        return INTENT_KIND_PLAN
    if fields.done_text:
        return INTENT_KIND_DONE
    return INTENT_KIND_OTHER


def summarize_intents(kinds: list[str]) -> str:
    """Build a short Russian "auto-split" summary line.

    Example output for ['done','done','done','done','plan','plan','risk']:
        "Разобрано: 7 пунктов · 4 сделано · 2 плана · 1 риск"

    Returns "" when there are fewer than 2 items (no value in showing it).
    """
    cleaned = [kind for kind in kinds if kind in VALID_INTENT_KINDS]
    total = len(cleaned)
    if total < 2:
        return ""
    counts: dict[str, int] = {}
    for kind in cleaned:
        counts[kind] = counts.get(kind, 0) + 1
    # Stable order matching VALID_INTENT_KINDS — most "doer" first.
    parts = [
        f"{counts[kind]} {INTENT_PLURAL_LABELS[kind]}"
        for kind in VALID_INTENT_KINDS
        if counts.get(kind, 0) > 0
    ]
    return f"Разобрано: {total} {_pluralize_points(total)} · " + " · ".join(parts)


def _is_empty_risk_marker(value: str) -> bool:
    cleaned = value.strip().lower()
    if not cleaned:
        return True
    return cleaned in {"нет", "нет.", "отсутствуют", "отсутствует", "без изменений", "none", "-"}


def _pluralize_points(count: int) -> str:
    last_two = count % 100
    last_one = count % 10
    if 11 <= last_two <= 14:
        return "пунктов"
    if last_one == 1:
        return "пункт"
    if 2 <= last_one <= 4:
        return "пункта"
    return "пунктов"
