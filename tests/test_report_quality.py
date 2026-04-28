"""End-to-end report-quality regression tests for Step 25.

Covers the demo scenario described in the user-facing TZ:
- Long PM monolog mentions Delivery Reports / Bank Dashboard /
  BONUS-2055 cashback project.
- Each atom is split, classified by intent, attached to the right
  project via aliases.
- Saved-note message and final draft are clean: no synthetic
  prefix duplication, no "Проект: X." bullets, no false blockers.
"""
from __future__ import annotations

import unittest
from datetime import date

from delivery_reports.repository import Note, Project
from delivery_reports.services.draft_builder import build_daily_draft
from delivery_reports.services.long_update_split import split_long_update
from delivery_reports.services.parsing import parse_note_blocks
from delivery_reports.services.report_text_cleaner import clean_report_item_text


def _project(id_: int, name: str, aliases: list[str], is_special: bool = False) -> Project:
    return Project(
        id=id_,
        owner_user_id=100,
        name=name,
        manager_name="",
        lead_name="",
        jira_base_url="",
        aliases=aliases,
        is_special_control=is_special,
    )


# ── Alias / project recognition ────────────────────────────────────────


class AliasRecognitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.projects = [
            _project(1, "Delivery Reports", ["Delivery", "PM Digest", "DR"]),
            _project(2, "Bank Dashboard", ["Bank", "BankDash", "BD"]),
            _project(
                3,
                "Внедрение категорийного кэшбэка (BONUS-2055)",
                ["BONUS-2055", "BONUS", "Кэшбэк", "MCC", "ГТС", "МФС", "Антифрод"],
                is_special=True,
            ),
        ]

    def test_delivery_alias_maps_to_full_project(self) -> None:
        atoms = split_long_update(
            "По Delivery Reports закрыли мобильную верстку. "
            "Завтра доделаем cache busting. "
            "Завтра доделаем mobile topnav.",
            self.projects,
        )
        self.assertGreaterEqual(len(atoms), 2)
        for atom in atoms:
            self.assertEqual(atom.project_name_hint, "Delivery Reports")

    def test_bank_alias_maps_to_full_project(self) -> None:
        atoms = split_long_update(
            "По Bank Dashboard обсудили интеграцию отчётов с Jira. "
            "Решение: на MVP оставить voice через Telegram. "
            "Блокер: нет доступа к Jira API.",
            self.projects,
        )
        self.assertGreaterEqual(len(atoms), 2)
        for atom in atoms:
            self.assertEqual(atom.project_name_hint, "Bank Dashboard")

    def test_short_alias_bank_alone_resolves(self) -> None:
        atoms = split_long_update(
            "По Bank сделали обзор задач. Завтра делаем демо.",
            self.projects,
        )
        self.assertTrue(all(a.project_name_hint == "Bank Dashboard" for a in atoms))

    def test_numeric_only_alias_2055_maps_to_cashback_project(self) -> None:
        # Add the numeric alias matching the demo seeder configuration.
        self.projects[2] = _project(
            3,
            "Внедрение категорийного кэшбэка (BONUS-2055)",
            ["BONUS-2055", "2055", "BONUS", "MCC", "ГТС", "МФС", "Антифрод", "High Risk Visa"],
            is_special=True,
        )
        atoms = split_long_update(
            "По 2055 закрыли финальные тесты. Завтра запускаем продакшен.",
            self.projects,
        )
        self.assertGreaterEqual(len(atoms), 1)
        for atom in atoms:
            self.assertEqual(
                atom.project_name_hint,
                "Внедрение категорийного кэшбэка (BONUS-2055)",
            )

    def test_bonus_2055_alias_maps_to_cashback_project(self) -> None:
        atoms = split_long_update(
            "По BONUS-2055 разработали MCC-классификатор. "
            "Завтра дорабатываем антифрод-правила.",
            self.projects,
        )
        self.assertEqual(len(atoms), 2)
        for atom in atoms:
            self.assertEqual(
                atom.project_name_hint,
                "Внедрение категорийного кэшбэка (BONUS-2055)",
            )

    def test_cyrillic_short_alias_gts_resolves(self) -> None:
        atoms = split_long_update(
            "По ГТС подписали интеграционный контракт. "
            "Антифрод подтвердил квоту.",
            self.projects,
        )
        for atom in atoms:
            self.assertEqual(
                atom.project_name_hint,
                "Внедрение категорийного кэшбэка (BONUS-2055)",
            )

    def test_unknown_short_token_does_not_match(self) -> None:
        atoms = split_long_update(
            "Сделали ID-проверку для авторизации. Завтра тестируем.",
            self.projects,
        )
        # "ID" is too short / not a known alias → no project.
        self.assertTrue(all(a.project_name_hint == "" for a in atoms))


# ── Intent classifier strictness ───────────────────────────────────────


class IntentStrictnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.projects = [
            _project(1, "Delivery Reports", ["Delivery"]),
            _project(2, "Bank Dashboard", ["Bank"]),
        ]

    def test_neutral_word_list_is_not_blocker(self) -> None:
        atoms = split_long_update(
            "Сделал редактор отчёта: добавил бейджи для сделано, план, риск и блокер.",
            self.projects,
        )
        self.assertEqual(len(atoms), 1)
        self.assertEqual(atoms[0].intent, "done")

    def test_explicit_blocker_is_blocker(self) -> None:
        atoms = split_long_update(
            "По Bank Dashboard обсудили API. "
            "Блокер по Bank Dashboard: нет доступа к Jira API.",
            self.projects,
        )
        blockers = [a for a in atoms if a.intent == "blocker"]
        self.assertEqual(len(blockers), 1)

    def test_explicit_risk_is_risk(self) -> None:
        atoms = split_long_update(
            "По Delivery Reports мобильный topnav готов. "
            "Риск по Delivery Reports: Telegram WebView может закэшировать ассеты.",
            self.projects,
        )
        risks = [a for a in atoms if a.intent == "risk"]
        self.assertEqual(len(risks), 1)

    def test_explicit_plan_is_plan(self) -> None:
        atoms = split_long_update(
            "По Delivery Reports закончили рефакторинг. "
            "План по Delivery Reports на завтра: дописать тесты.",
            self.projects,
        )
        plans = [a for a in atoms if a.intent == "plan"]
        self.assertEqual(len(plans), 1)

    def test_explicit_question_is_question(self) -> None:
        atoms = split_long_update(
            "По Bank Dashboard готов прототип. "
            "Вопрос по Bank Dashboard: кто будет владельцем справочника?",
            self.projects,
        )
        questions = [a for a in atoms if a.intent == "question"]
        self.assertGreaterEqual(len(questions), 1)

    def test_no_access_phrase_is_blocker(self) -> None:
        atoms = split_long_update(
            "Сделали обзор API. Нет доступа к Jira API.",
            self.projects,
        )
        blockers = [a for a in atoms if a.intent == "blocker"]
        self.assertEqual(len(blockers), 1)

    def test_neutral_done_text_is_done_not_blocker(self) -> None:
        # The buggy substring-match would have returned "blocker" because
        # "блокер" appears in this sentence.  Strict rules must NOT trip.
        atoms = split_long_update(
            "Обсудили формат бейджа для блокера и риска.",
            self.projects,
        )
        self.assertEqual(len(atoms), 1)
        self.assertNotEqual(atoms[0].intent, "blocker")
        self.assertNotEqual(atoms[0].intent, "risk")


# ── clean_report_item_text helper ──────────────────────────────────────


class CleanReportItemTextTests(unittest.TestCase):
    def test_strips_synthetic_question_prefix(self) -> None:
        out = clean_report_item_text("вопрос — Вопрос по Bank Dashboard: кто владелец?")
        self.assertEqual(out, "Кто владелец?")

    def test_strips_synthetic_blocker_prefix(self) -> None:
        out = clean_report_item_text("блокер — Блокер по Bank Dashboard: нет доступа к Jira API")
        self.assertEqual(out, "Нет доступа к Jira API")

    def test_strips_synthetic_decision_prefix(self) -> None:
        out = clean_report_item_text("решение — Решение по Bank Dashboard: на MVP оставить voice")
        self.assertEqual(out, "На MVP оставить voice")

    def test_strips_user_typed_blocker_label_only(self) -> None:
        out = clean_report_item_text("Блокер: нет доступа к Jira API")
        self.assertEqual(out, "Нет доступа к Jira API")

    def test_strips_user_typed_blocker_label_with_project(self) -> None:
        out = clean_report_item_text("Блокер по Bank Dashboard: нет доступа к Jira API")
        self.assertEqual(out, "Нет доступа к Jira API")

    def test_drops_pure_project_label_line(self) -> None:
        self.assertEqual(clean_report_item_text("Проект: Delivery."), "")
        self.assertEqual(clean_report_item_text("проект: bank dashboard"), "")

    def test_passes_through_clean_text(self) -> None:
        self.assertEqual(
            clean_report_item_text("Сделал редактор отчёта"),
            "Сделал редактор отчёта",
        )

    def test_handles_empty_input(self) -> None:
        self.assertEqual(clean_report_item_text(""), "")
        self.assertEqual(clean_report_item_text("   "), "")
        self.assertEqual(clean_report_item_text(None), "")  # type: ignore[arg-type]

    def test_strips_what_done_heading(self) -> None:
        out = clean_report_item_text("Что сделано: интеграция API")
        self.assertEqual(out, "Интеграция API")

    def test_idempotent_on_already_clean_text(self) -> None:
        once = clean_report_item_text("Нет доступа к Jira API")
        twice = clean_report_item_text(once)
        self.assertEqual(once, twice)


# ── Final draft hygiene ────────────────────────────────────────────────


class FinalDraftHygieneTests(unittest.TestCase):
    """End-to-end: parse → save → render. The output must be clean."""

    def setUp(self) -> None:
        self.projects = [
            _project(1, "Delivery Reports", ["Delivery"]),
            _project(2, "Bank Dashboard", ["Bank"]),
        ]
        self.target_date = date(2026, 4, 28)

    def _build_notes_from_text(self, raw_text: str) -> list[Note]:
        """Mini pipeline: parse blocks → fake Note objects (no DB)."""
        blocks = parse_note_blocks(raw_text, self.projects)
        notes: list[Note] = []
        for index, block in enumerate(blocks, start=1):
            parsed = block.parsed
            project_id = parsed.project_id
            notes.append(
                Note(
                    id=index,
                    note_date=self.target_date.isoformat(),
                    user_id=100,
                    source="text",
                    raw_text=block.raw_text,
                    project_id=project_id,
                    manager_name="Анатолий",
                    lead_name="Дмитрий",
                    epic="",
                    status_text=parsed.status_text,
                    done_text=parsed.done_text,
                    plan_text=parsed.plan_text,
                    risk_text=parsed.risk_text,
                    jira_links=parsed.jira_links,
                    needs_review=parsed.needs_review,
                )
            )
        return notes

    def test_draft_has_no_duplicated_prefix_text(self) -> None:
        text = (
            "По Bank Dashboard обсудили API. "
            "Блокер по Bank Dashboard: нет доступа к Jira API. "
            "Решение по Bank Dashboard: на MVP оставить voice. "
            "Вопрос по Bank Dashboard: кто будет владельцем справочника?"
        )
        notes = self._build_notes_from_text(text)
        draft = build_daily_draft(
            target_date=self.target_date,
            notes=notes,
            projects=self.projects,
            default_manager_name="Анатолий",
            default_lead_name="Дмитрий",
        )
        self.assertNotIn("Вопрос — Вопрос", draft)
        self.assertNotIn("вопрос — Вопрос", draft)
        self.assertNotIn("Блокер — Блокер", draft)
        self.assertNotIn("блокер — Блокер", draft)
        self.assertNotIn("Решение — Решение", draft)
        self.assertNotIn("решение — Решение", draft)

    def test_draft_has_no_project_label_bullet(self) -> None:
        text = (
            "По Delivery Reports сделали мобильную верстку. "
            "Завтра доделаем cache busting."
        )
        notes = self._build_notes_from_text(text)
        draft = build_daily_draft(
            target_date=self.target_date,
            notes=notes,
            projects=self.projects,
            default_manager_name="Анатолий",
            default_lead_name="Дмитрий",
        )
        self.assertNotIn("• Проект:", draft)
        self.assertNotIn("- Проект:", draft)
        self.assertNotIn("Проект: Delivery", draft.replace("📌 <b>Delivery", ""))

    def test_unknown_project_routes_to_inbox_section(self) -> None:
        text = "Сделали что-то очень общее."
        notes = self._build_notes_from_text(text)
        draft = build_daily_draft(
            target_date=self.target_date,
            notes=notes,
            projects=self.projects,
            default_manager_name="Анатолий",
            default_lead_name="Дмитрий",
        )
        # Unknown project → "📥 Нужно уточнить проект" section header.
        self.assertIn("📥 <b>Нужно уточнить проект</b>", draft)

    def test_draft_uses_project_emoji_for_recognized(self) -> None:
        text = "По Delivery Reports сделали тесты. Завтра делаем демо."
        notes = self._build_notes_from_text(text)
        draft = build_daily_draft(
            target_date=self.target_date,
            notes=notes,
            projects=self.projects,
            default_manager_name="Анатолий",
            default_lead_name="Дмитрий",
        )
        self.assertIn("📌 <b>Delivery Reports</b>", draft)


if __name__ == "__main__":
    unittest.main()
