from __future__ import annotations

import unittest

from delivery_reports.repository import Project
from delivery_reports.services.long_update_split import (
    AtomicUpdate,
    looks_long_unstructured,
    split_long_update,
)


def _project(id_: int, name: str, aliases: list[str]) -> Project:
    return Project(
        id=id_,
        owner_user_id=100,
        name=name,
        manager_name="",
        lead_name="",
        jira_base_url="",
        aliases=aliases,
        is_special_control=False,
    )


class LongUpdateSplitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.projects = [
            _project(1, "DC701", ["цод", "dc701"]),
            _project(2, "Caller ID", ["callerid", "caller-id"]),
        ]

    # ── Sanity ──────────────────────────────────────────────
    def test_short_text_is_not_split(self) -> None:
        atoms = split_long_update("короткая заметка", self.projects)
        self.assertEqual(len(atoms), 1)
        self.assertEqual(atoms[0].text, "короткая заметка")
        self.assertEqual(atoms[0].intent, "other")

    def test_empty_text_returns_empty(self) -> None:
        self.assertEqual(split_long_update("", self.projects), [])
        self.assertEqual(split_long_update("   \n  ", self.projects), [])

    def test_looks_long_thresholds(self) -> None:
        self.assertFalse(looks_long_unstructured("короткое"))
        self.assertTrue(looks_long_unstructured("Сделал. Завтра демо. Блокер тут."))
        self.assertTrue(looks_long_unstructured("a" * 250))

    # ── Core scenario: dictated monolog with 3 distinct items ──
    def test_splits_done_plan_blocker_with_carry_over(self) -> None:
        text = (
            "Закрыли релиз 2.4 по проекту DC701 сегодня утром. "
            "Завтра планирую провести демо с заказчиком. "
            "Блокер: ждём ответ от подрядчика по железу."
        )
        atoms = split_long_update(text, self.projects)

        intents = [a.intent for a in atoms]
        self.assertIn("done", intents)
        self.assertIn("plan", intents)
        self.assertIn("blocker", intents)
        # Project carries over from sentence 1 to sentences 2-3.
        for atom in atoms:
            self.assertEqual(atom.project_name_hint, "DC701")

    # ── Project switch resets carry-over ─────────────────────
    def test_project_switch_resets_carry_over(self) -> None:
        text = (
            "По проекту DC701 закрыли миграцию серверов. "
            "Завтра делаем финальный отчёт. "
            "Теперь по другому проекту: по Caller ID релизнули новую витрину. "
            "Завтра планируем смотреть метрики."
        )
        atoms = split_long_update(text, self.projects)
        self.assertGreaterEqual(len(atoms), 3)
        first = next(a for a in atoms if "миграцию" in a.text.lower())
        self.assertEqual(first.project_name_hint, "DC701")
        caller = next(a for a in atoms if "витрину" in a.text.lower())
        self.assertEqual(caller.project_name_hint, "Caller ID")
        # The "завтра планируем смотреть метрики" should still be Caller ID via carry.
        last_plan = [a for a in atoms if a.intent == "plan"][-1]
        self.assertEqual(last_plan.project_name_hint, "Caller ID")

    # ── Question detection ──────────────────────────────────
    def test_question_intent_from_trailing_qmark(self) -> None:
        text = (
            "Закрыли задачу по DC701. "
            "Кто согласует бюджет на следующий квартал?"
        )
        atoms = split_long_update(text, self.projects)
        intents = [a.intent for a in atoms]
        self.assertIn("question", intents)

    # ── Alias-based project detection ───────────────────────
    def test_alias_match_detects_project(self) -> None:
        text = (
            "По цод закрыли освобождение здания. "
            "Завтра подписываем акты. "
            "Риск: подрядчик ещё не подтвердил доставку."
        )
        atoms = split_long_update(text, self.projects)
        self.assertGreaterEqual(len(atoms), 2)
        self.assertTrue(all(a.project_name_hint == "DC701" for a in atoms))

    # ── Merge adjacent same-intent items ────────────────────
    def test_adjacent_done_items_are_merged(self) -> None:
        text = (
            "Сделали А по DC701. Сделали Б по DC701. Сделали В по DC701. "
            "Завтра — демо."
        )
        atoms = split_long_update(text, self.projects)
        done_atoms = [a for a in atoms if a.intent == "done"]
        # Should be merged into 1 done block (small enough total size).
        self.assertEqual(len(done_atoms), 1)
        self.assertIn("А", done_atoms[0].text)
        self.assertIn("Б", done_atoms[0].text)
        self.assertIn("В", done_atoms[0].text)


if __name__ == "__main__":
    unittest.main()
