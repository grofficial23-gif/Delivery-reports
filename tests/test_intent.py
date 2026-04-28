from __future__ import annotations

import unittest

from delivery_reports.services.intent import (
    INTENT_KIND_BLOCKER,
    INTENT_KIND_DECISION,
    INTENT_KIND_DONE,
    INTENT_KIND_OTHER,
    INTENT_KIND_PLAN,
    INTENT_KIND_QUESTION,
    INTENT_KIND_RISK,
    INTENT_LABELS,
    infer_intent_kind,
    label_for_kind,
    summarize_intents,
)


class IntentInferenceTests(unittest.TestCase):
    def test_done_when_only_done_text_present(self) -> None:
        self.assertEqual(infer_intent_kind(done_text="закрыли релиз"), INTENT_KIND_DONE)

    def test_plan_when_plan_text_present(self) -> None:
        self.assertEqual(
            infer_intent_kind(done_text="что-то", plan_text="завтра демо"),
            INTENT_KIND_PLAN,
        )

    def test_risk_when_risk_text_present(self) -> None:
        self.assertEqual(
            infer_intent_kind(risk_text="подрядчик может уехать"),
            INTENT_KIND_RISK,
        )

    def test_blocker_when_risk_text_starts_with_blocker_marker(self) -> None:
        self.assertEqual(
            infer_intent_kind(risk_text="блокер — ждём ответ от подрядчика"),
            INTENT_KIND_BLOCKER,
        )

    def test_decision_prefix_in_done_text(self) -> None:
        self.assertEqual(
            infer_intent_kind(done_text="решение — согласовали бюджет"),
            INTENT_KIND_DECISION,
        )

    def test_question_prefix_in_done_text(self) -> None:
        self.assertEqual(
            infer_intent_kind(done_text="вопрос — кто согласует бюджет"),
            INTENT_KIND_QUESTION,
        )

    def test_other_when_everything_empty(self) -> None:
        self.assertEqual(infer_intent_kind(), INTENT_KIND_OTHER)

    def test_empty_risk_marker_does_not_promote_to_risk(self) -> None:
        # Common pattern: risk_text == "нет" — must not light up the badge.
        self.assertEqual(
            infer_intent_kind(done_text="закрыли релиз", risk_text="нет"),
            INTENT_KIND_DONE,
        )


class IntentLabelTests(unittest.TestCase):
    def test_label_for_kind_returns_expected_glyphs(self) -> None:
        self.assertEqual(label_for_kind(INTENT_KIND_DONE), "✓ Сделано")
        self.assertEqual(label_for_kind(INTENT_KIND_PLAN), "→ План")
        self.assertEqual(label_for_kind(INTENT_KIND_RISK), "⚠ Риск")
        self.assertEqual(label_for_kind(INTENT_KIND_BLOCKER), "⛔ Блокер")
        self.assertEqual(label_for_kind(INTENT_KIND_DECISION), "◆ Решение")
        self.assertEqual(label_for_kind(INTENT_KIND_QUESTION), "? Вопрос")
        self.assertEqual(label_for_kind(INTENT_KIND_OTHER), "• Апдейт")

    def test_unknown_kind_falls_back_to_other_label(self) -> None:
        self.assertEqual(label_for_kind("nope"), INTENT_LABELS[INTENT_KIND_OTHER])


class SummarizeIntentsTests(unittest.TestCase):
    def test_returns_empty_for_single_item(self) -> None:
        self.assertEqual(summarize_intents([INTENT_KIND_DONE]), "")

    def test_groups_and_pluralizes_correctly(self) -> None:
        summary = summarize_intents(
            [
                INTENT_KIND_DONE, INTENT_KIND_DONE, INTENT_KIND_DONE, INTENT_KIND_DONE,
                INTENT_KIND_PLAN, INTENT_KIND_PLAN,
                INTENT_KIND_RISK,
            ]
        )
        # 7 пунктов · 4 сделано · 2 плана · 1 риск
        self.assertIn("Разобрано: 7 пунктов", summary)
        self.assertIn("4 сделано", summary)
        self.assertIn("2 плана", summary)
        self.assertIn("1 риск", summary)

    def test_pluralization_for_one(self) -> None:
        summary = summarize_intents([INTENT_KIND_DONE, INTENT_KIND_PLAN])
        # 2 пункта (не "пунктов")
        self.assertIn("Разобрано: 2 пункта", summary)


if __name__ == "__main__":
    unittest.main()
