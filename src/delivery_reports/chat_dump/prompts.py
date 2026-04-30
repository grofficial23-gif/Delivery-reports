"""Prompts and strict JSON schema for chat-dump fact extraction (no jsonschema dep)."""

from __future__ import annotations

# OpenAI strict json_schema + Anthropic tool input_schema (same shape).
DUMP_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["facts", "skipped"],
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "type",
                    "text",
                    "confidence",
                    "project_hint",
                    "suggested_project_id",
                ],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "done",
                            "plan",
                            "risk",
                            "blocker",
                            "decision",
                            "question",
                            "note",
                        ],
                    },
                    "text": {"type": "string"},
                    "confidence": {"type": "number"},
                    "project_hint": {"type": ["string", "null"]},
                    "suggested_project_id": {"type": ["integer", "null"]},
                },
            },
        },
        "skipped": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["reason", "snippet"],
                "properties": {
                    "reason": {"type": "string"},
                    "snippet": {"type": ["string", "null"]},
                },
            },
        },
    },
}


FACT_TYPES = frozenset(
    {"done", "plan", "risk", "blocker", "decision", "question", "note"}
)


def system_prompt() -> str:
    return """Ты извлекаешь атомарные факты из переписки/дампа статуса менеджера для рабочего отчёта.

Правила:
- Каждый факт — одна короткая самодостаточная строка, близкая к оригиналу; не выдумывай.
- Тип: done (сделано), plan (план), risk, blocker, decision, question, note (прочее).
- confidence — от 0 до 1, насколько уверен в типе и формулировке.
- project_hint — название/токен проекта из контекста или null.
- suggested_project_id — только если явно указан числовой id в тексте, иначе null.
- В skipped попадай шум: приветствия, пустые фразы, оффтоп без факта; укажи reason и короткий snippet.

Ответ строго один JSON-объект по схеме инструмента, без текста до/после."""


def user_prompt(*, cleaned_text: str, user_lang: str) -> str:
    return f"""Язык интерфейса: {user_lang}

Очищенный текст дампа:

---
{cleaned_text}
---

Верни JSON с полями facts и skipped."""
