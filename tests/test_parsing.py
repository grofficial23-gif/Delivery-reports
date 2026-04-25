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
