from __future__ import annotations

import unittest

from delivery_reports.services.smart_input import parse_smart_input


class SmartInputTests(unittest.TestCase):
    def test_parses_status_shortcut(self) -> None:
        action = parse_smart_input("статус")
        self.assertIsNotNone(action)
        self.assertEqual(action.kind, "status")

    def test_parses_day_overview_shortcut(self) -> None:
        action = parse_smart_input("что уже добавлено")
        self.assertIsNotNone(action)
        self.assertEqual(action.kind, "status")

    def test_parses_task_add_shortcut(self) -> None:
        action = parse_smart_input("задача: согласовать окно ночных работ")
        self.assertIsNotNone(action)
        self.assertEqual(action.kind, "add_task")
        self.assertEqual(action.text, "согласовать окно ночных работ")

    def test_parses_task_done_shortcut(self) -> None:
        action = parse_smart_input("готово 12")
        self.assertIsNotNone(action)
        self.assertEqual(action.kind, "task_done")
        self.assertEqual(action.task_id, 12)

    def test_parses_inbox_resolve_shortcut(self) -> None:
        action = parse_smart_input("разобрать 15 DC701")
        self.assertIsNotNone(action)
        self.assertEqual(action.kind, "resolve_inbox")
        self.assertEqual(action.task_id, 15)
        self.assertEqual(action.project_name, "DC701")

    def test_returns_none_for_regular_note(self) -> None:
        self.assertIsNone(parse_smart_input("сегодня закрыли аналитику и ждем окно"))


if __name__ == "__main__":
    unittest.main()
