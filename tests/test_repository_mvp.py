from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from delivery_reports.db import Database
from delivery_reports.repository import NewNote, NewPMTask, Repository


class RepositoryMvpTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp_dir.name) / "test.db"
        self.repository = Repository(Database(db_path))

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_default_templates_seeded(self) -> None:
        self.repository.ensure_default_report_templates()
        templates = self.repository.list_report_templates(active_only=True)
        keys = [item.template_key for item in templates]
        self.assertIn("standard", keys)
        self.assertIn("concise", keys)
        self.assertIn("risk_focus", keys)
        self.assertIn("team", keys)
        default_template = self.repository.get_default_report_template()
        self.assertIsNotNone(default_template)
        self.assertEqual(default_template.template_key, "standard")

    def test_save_and_read_final_report(self) -> None:
        target_date = date(2026, 4, 24)
        content = "<b>Final report</b>"
        self.repository.save_final_report(target_date=target_date, content=content, author_user_id=42)
        stored = self.repository.get_latest_final_report_for_date(target_date, author_user_id=42)
        self.assertEqual(stored, content)

    def test_save_and_read_draft_for_specific_user(self) -> None:
        target_date = date(2026, 4, 24)
        self.repository.save_draft(target_date=target_date, content="<b>User 42</b>", owner_user_id=42)
        self.repository.save_draft(target_date=target_date, content="<b>User 77</b>", owner_user_id=77)

        self.assertEqual(
            self.repository.get_latest_draft_for_date(target_date, owner_user_id=42),
            "<b>User 42</b>",
        )
        self.assertEqual(
            self.repository.get_latest_draft_for_date(target_date, owner_user_id=77),
            "<b>User 77</b>",
        )

    def test_projects_are_isolated_by_owner(self) -> None:
        self.repository.upsert_project(
            name="DC701",
            manager_name="A",
            lead_name="B",
            jira_base_url="",
            aliases=["dc701"],
            is_special_control=False,
            owner_user_id=42,
        )
        self.repository.upsert_project(
            name="DC701",
            manager_name="C",
            lead_name="D",
            jira_base_url="",
            aliases=["dc701"],
            is_special_control=False,
            owner_user_id=77,
        )

        user_42_project = self.repository.find_project_by_name_or_alias("DC701", owner_user_id=42)
        user_77_project = self.repository.find_project_by_name_or_alias("DC701", owner_user_id=77)

        self.assertIsNotNone(user_42_project)
        self.assertIsNotNone(user_77_project)
        self.assertNotEqual(user_42_project.owner_user_id, user_77_project.owner_user_id)

    def test_add_and_update_pm_tasks(self) -> None:
        task_id = self.repository.add_task(
            NewPMTask(
                owner_user_id=42,
                title="Проверить согласование ночного окна",
                status="open",
            )
        )
        tasks = self.repository.list_tasks_for_user(42, statuses=["open"])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, task_id)
        updated = self.repository.update_task_status(task_id, 42, "done")
        self.assertTrue(updated)
        done_tasks = self.repository.list_tasks_for_user(42, statuses=["done"])
        self.assertEqual(len(done_tasks), 1)
        self.assertEqual(done_tasks[0].id, task_id)

    def test_list_unresolved_notes_for_user(self) -> None:
        self.repository.add_note(
            NewNote(
                note_date=date(2026, 4, 24).isoformat(),
                user_id=42,
                source="text",
                raw_text="какой-то апдейт без проекта",
                status_text="в работе",
                needs_review=True,
            )
        )
        unresolved = self.repository.list_unresolved_notes_for_user(42, target_date=date(2026, 4, 24))
        self.assertEqual(len(unresolved), 1)
        self.assertTrue(unresolved[0].needs_review)
        self.assertEqual(unresolved[0].status_text, "в работе")


if __name__ == "__main__":
    unittest.main()
