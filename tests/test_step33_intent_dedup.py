"""Step 33 — stricter risk routing + cross-section bullet dedup."""
from __future__ import annotations

import unittest
from datetime import date

from delivery_reports.repository import Note, Project
from delivery_reports.services.draft_builder import build_daily_draft
from delivery_reports.services.long_update_split import split_long_update
from delivery_reports.services.parsing import parse_note_blocks


def _p(i: int, name: str, aliases: list[str]) -> Project:
    return Project(
        id=i,
        owner_user_id=100,
        name=name,
        manager_name="",
        lead_name="",
        jira_base_url="",
        aliases=aliases,
        is_special_control=False,
    )


class Step33ClassificationTests(unittest.TestCase):
    def test_problem_in_sdk_phrase_not_risk(self) -> None:
        atoms = split_long_update(
            "Проблема в закрытой логике SDK MyID: SDK принудительно отдаёт обрезанное изображение 720x720.",
            [],
        )
        self.assertTrue(atoms)
        self.assertNotIn("risk", [a.intent for a in atoms])

    def test_uniform_not_we_decision(self) -> None:
        atoms = split_long_update(
            "Унифицировать формат на нашей стороне не будем.",
            [],
        )
        self.assertEqual(len(atoms), 1)
        self.assertEqual(atoms[0].intent, "decision")

    def test_myid_conditional_rationale_is_decision_not_risk(self) -> None:
        atoms = split_long_update(
            "Если начнём программно изменять картинку после SDK, можем сломать серверную валидацию MyID.",
            [],
        )
        self.assertEqual(len(atoms), 1)
        self.assertEqual(atoms[0].intent, "decision")

    def test_explicit_risk_onboarding_stays_risk(self) -> None:
        atoms = split_long_update(
            "Риск по Onboarding: возможна задержка.",
            [],
        )
        self.assertEqual(len(atoms), 1)
        self.assertEqual(atoms[0].intent, "risk")


class Step33DraftDedupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.projects = [_p(1, "Onboarding + Identification", ["Onboarding", "MyID"])]
        self.target_date = date(2026, 4, 28)

    def _notes_from_raw(self, raw: str) -> list[Note]:
        blocks = parse_note_blocks(raw, self.projects)
        notes: list[Note] = []
        for i, block in enumerate(blocks, start=1):
            p = block.parsed
            notes.append(
                Note(
                    id=i,
                    note_date=self.target_date.isoformat(),
                    user_id=100,
                    source="text",
                    raw_text=block.raw_text,
                    project_id=p.project_id,
                    manager_name="M",
                    lead_name="L",
                    epic="",
                    status_text=p.status_text,
                    done_text=p.done_text,
                    plan_text=p.plan_text,
                    risk_text=p.risk_text,
                    jira_links=p.jira_links,
                    needs_review=p.needs_review,
                )
            )
        return notes

    def test_myid_sample_no_risks_section_has_decision(self) -> None:
        raw = (
            "По Onboarding краткий статус по проблеме с форматом фото 1:1 при FA на Xiaomi Redmi Note 8 Pro. "
            "Анализ завершили. "
            "Проблема в закрытой логике SDK MyID: SDK принудительно отдаёт обрезанное изображение 720x720. "
            "Унифицировать формат на нашей стороне не будем. "
            "Если начнём программно изменять картинку после SDK, можем сломать серверную валидацию MyID. "
            "Таску на анализ со стороны разработки закрыли."
        )
        notes = self._notes_from_raw(raw)
        draft = build_daily_draft(
            target_date=self.target_date,
            notes=notes,
            projects=self.projects,
            default_manager_name="M",
            default_lead_name="L",
        )
        self.assertNotIn("⚠️ Риски", draft)
        self.assertIn("◆ Решение", draft)
        self.assertIn("✅ Что сделано", draft)

    def test_duplicate_line_risk_and_done_deduped_to_risk_only(self) -> None:
        line = "Одинаковая строка для дедупа."
        note = Note(
            id=1,
            note_date=self.target_date.isoformat(),
            user_id=100,
            source="text",
            raw_text="",
            project_id=1,
            manager_name="M",
            lead_name="L",
            epic="",
            status_text="",
            done_text="Уникальный пункт только в сделано.\n" + line + "\n",
            plan_text="",
            risk_text="Риск: " + line + "\n",
            jira_links=[],
            needs_review=False,
        )
        draft = build_daily_draft(
            target_date=self.target_date,
            notes=[note],
            projects=self.projects,
            default_manager_name="M",
            default_lead_name="L",
        )
        self.assertEqual(draft.count("Одинаковая строка для дедупа"), 1)
        self.assertIn("⚠️ Риски", draft)
        self.assertIn("✅ Что сделано", draft)
        risk_pos = draft.find("⚠️ Риски")
        done_pos = draft.find("✅ Что сделано")
        dup_pos = draft.find("Одинаковая строка для дедупа")
        self.assertLess(done_pos, risk_pos)
        self.assertGreater(dup_pos, risk_pos)


if __name__ == "__main__":
    unittest.main()
