"""Prompts and JSON schema for smart compose."""

from __future__ import annotations

OUTPUT_JSON_SCHEMA: dict = {
    "type": "object",
    "required": ["kept", "excluded"],
    "additionalProperties": False,
    "properties": {
        "kept": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["project_id", "type", "text", "source_ids", "salience"],
                "additionalProperties": False,
                "properties": {
                    "project_id": {"type": ["integer", "null"]},
                    "type": {
                        "enum": [
                            "done",
                            "plan",
                            "risk",
                            "blocker",
                            "decision",
                            "question",
                            "note",
                        ]
                    },
                    "text": {"type": "string", "maxLength": 500},
                    "source_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 1,
                    },
                    "salience": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "excluded": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source_id", "reason"],
                "additionalProperties": False,
                "properties": {
                    "source_id": {"type": "integer"},
                    "reason": {
                        "enum": [
                            "duplicate",
                            "low_signal",
                            "false_risk",
                            "false_blocker",
                            "off_topic",
                            "incomplete",
                        ]
                    },
                    "duplicate_of": {"type": ["integer", "null"]},
                    "note": {"type": ["string", "null"], "maxLength": 100},
                },
            },
        },
    },
}


def system_prompt() -> str:
    return """Ты помощник делового отчёта. Твоя задача — взять список рабочих апдейтов сотрудника и подготовить их для финального отчёта руководителю.

Жёсткие правила:
- НЕ переписывай и не сокращай сами апдейты — оставляй формулировки максимально близкими к оригиналу. Можешь только склеивать дубликаты в одну строку, выбирая самую полную формулировку.
- НИКОГДА не помечай как риск/блокер фразы «риск: нет», «блокеров нет», «всё ок», «рисков пока не вижу». Это не риски и не блокеры.
- Слово «проблема» в нейтральном контексте («обсудили проблему ретеншна») — это НЕ риск.
- Если апдейт состоит из одного слова или междометия («ок», «👍», «хорошо», «work in progress») — excluded с reason low_signal.
- Если две заметки внутри ОДНОГО проекта говорят об одном и том же — оставь одну (более полную), вторую → excluded с reason duplicate, duplicate_of=<id первой>.
- Заметки между разными проектами НЕ дедуплицируются.
- Порядок ввода может не совпадать с порядком событий.
- Salience: 0.9–1.0 — критично (риски, блокеры, важные решения), 0.6–0.8 — значимо (закрытые задачи, ключевые планы), 0.3–0.5 — рутина, 0.0–0.2 — мелочь.
- Никогда не добавляй фактов, которых нет во входе.
- Ответ строго JSON по схеме. Никакого текста до или после JSON.

Примеры:
Вход: два done «Закрыл API» и «API готов» в одном проекте → одна строка kept с двумя source_ids, вторая excluded duplicate.
Вход: «Риск: нет» → excluded false_risk (или low_signal если это явно статус-заглушка).
Вход: DC701 два абзаца про одно и то же → duplicate внутри проекта DC701."""


FEW_SHOT_1 = """
Пример ответа для демонстрации формата (выдуманные id):
{"kept":[{"project_id":3,"type":"done","text":"Закрыл API авторизации","source_ids":[101,102],"salience":0.7},{"project_id":3,"type":"risk","text":"Деплой может затянуться из-за инфры","source_ids":[103],"salience":0.95}],"excluded":[{"source_id":104,"reason":"false_risk","duplicate_of":null,"note":"заглушка"},{"source_id":120,"reason":"low_signal","duplicate_of":null,"note":null}]}
"""


FEW_SHOT_2 = """
Ещё пример: note «ок» → excluded low_signal; разные проекты не дедуплицируются даже при похожем тексте.
"""


def user_prompt(
    *,
    report_date: str,
    template_label: str,
    template_key: str,
    user_lang: str,
    grouped_block: str,
) -> str:
    return f"""Дата отчёта: {report_date}
Шаблон: {template_key} ({template_label})
Язык: {user_lang}

Апдейты сгруппированы по проектам:

{grouped_block}

Верни JSON по схеме."""


COMPOSE_JSON_SCHEMA = OUTPUT_JSON_SCHEMA
SYSTEM_PROMPT = "\n\n".join([system_prompt(), FEW_SHOT_1.strip(), FEW_SHOT_2.strip()])
TEMPLATE_LABELS = {
    "concise": "Коротко",
    "risk_focus": "Для руководителя",
    "standard": "Полный",
    "team_examples": "Для команды",
    "team": "Для команды",
}
