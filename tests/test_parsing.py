from __future__ import annotations

import unittest

from delivery_reports.repository import Project
from delivery_reports.services.parsing import parse_note_blocks, parse_note_text


class ParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.projects = [
            Project(
                id=1,
                owner_user_id=100,
                name="DC701",
                manager_name="Анатолий",
                lead_name="Дмитрий",
                jira_base_url="https://jira.example.com",
                aliases=["цод", "dc701"],
                is_special_control=False,
            )
        ]

    def test_parses_structured_sections_and_status(self) -> None:
        parsed = parse_note_text(
            (
                "Дата: 09.04.2026\n"
                "Менеджер: Анатолий Графкин\n"
                "Руководитель: Дмитрий Кононенко\n"
                "Проект: DC701\n"
                "Статус: в работе\n"
                "Что сделано:\n"
                "- переносим виртуальные серверы\n"
                "План на завтра:\n"
                "- согласовать ночные окна\n"
                "Риски:\n"
                "- сжатые сроки по освобождению здания\n"
            ),
            self.projects,
        )

        self.assertEqual(parsed.status_text, "в работе")
        self.assertEqual(parsed.done_text, "переносим виртуальные серверы")
        self.assertEqual(parsed.plan_text, "согласовать ночные окна")
        self.assertEqual(parsed.risk_text, "сжатые сроки по освобождению здания")

    def test_splits_long_unstructured_monolog_into_atomic_blocks(self) -> None:
        text = (
            "Закрыли релиз 2.4 по проекту DC701 сегодня утром, "
            "ушли на ревью QA. "
            "Завтра планирую провести демо с заказчиком и собрать обратную связь. "
            "Блокер: ждём ответ от подрядчика по железу, без этого не уедем дальше."
        )
        blocks = parse_note_blocks(text, self.projects)

        self.assertGreaterEqual(len(blocks), 2)
        all_done = " ".join(b.parsed.done_text for b in blocks)
        all_plan = " ".join(b.parsed.plan_text for b in blocks)
        all_risk = " ".join(b.parsed.risk_text for b in blocks)
        self.assertIn("релиз", all_done.lower())
        self.assertIn("демо", all_plan.lower())
        self.assertIn("подрядчика", all_risk.lower())
        # Each atomic block must keep its raw fragment.
        self.assertTrue(all(b.raw_text.strip() for b in blocks))

    def test_short_text_does_not_invoke_long_split(self) -> None:
        blocks = parse_note_blocks("Сделал релиз DC701", self.projects)
        self.assertEqual(len(blocks), 1)

    def test_splits_blocks_when_message_contains_multiple_dates(self) -> None:
        blocks = parse_note_blocks(
            (
                "Дата: 09.04.2026\n"
                "Менеджер: Анатолий\n"
                "Проект: DC701\n"
                "Статус: в работе\n"
                "Что сделано:\n"
                "- первый блок\n"
                "\n"
                "Дата: 10.04.2026\n"
                "Менеджер: Анатолий\n"
                "Проект: DC701\n"
                "Статус: тестирование\n"
                "Что сделано:\n"
                "- второй блок\n"
            ),
            self.projects,
        )

        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].parsed.status_text, "в работе")
        self.assertEqual(blocks[1].parsed.status_text, "тестирование")


if __name__ == "__main__":
    unittest.main()
