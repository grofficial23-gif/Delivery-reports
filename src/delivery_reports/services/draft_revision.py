from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DraftRevisionRequest:
    style: str
    label: str


def parse_revision_instruction(text: str) -> DraftRevisionRequest | None:
    normalized = " ".join(text.strip().lower().split())
    if not normalized:
        return None

    if normalized in {"обычный", "обычно", "стандарт", "standard"}:
        return DraftRevisionRequest(style="standard", label="обычный")

    concise_tokens = ("короче", "кратко", "сжато", "сократи")
    if any(token in normalized for token in concise_tokens):
        return DraftRevisionRequest(style="concise", label="короче")

    risk_tokens = ("риск", "риски", "блокер", "акцент на риск", "фокус на риск")
    if any(token in normalized for token in risk_tokens):
        return DraftRevisionRequest(style="risk_focus", label="акцент на риск")

    team_tokens = ("командный", "по примерам", "как в команде", "как у команды", "team")
    if any(token in normalized for token in team_tokens):
        return DraftRevisionRequest(style="team_examples", label="командный")

    return None


def revision_help_text() -> str:
    return (
        "Напишите, как пересобрать черновик: `короче`, `акцент на риск`, `командный` или `обычный`."
    )
