from __future__ import annotations

import unittest
from datetime import date

from delivery_reports.repository import Note, Project
from delivery_reports.services.draft_builder import build_daily_draft


class DraftBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = Project(
            id=1,
            owner_user_id=100,
            name="Caller ID",
            manager_name="Анатолий Графкин",
            lead_name="Дмитрий Кононенко",
            jira_base_url="",
            aliases=["caller"],
            is_special_control=False,
        )
        self.target_date = date(2026, 4, 24)

    def test_standard_draft_contains_readable_sections(self) -> None:
        note = Note(
            id=1,
            note_date=self.target_date.isoformat(),
            user_id=100,
            source="text",
            raw_text="",
            project_id=1,
            manager_name="Анатолий Графкин",
            lead_name="Дмитрий Кононенко",
            epic="OM-33824",
            status_text="",
            done_text="завершили аналитику\nсинхронизировали матрицу событий",
            plan_text="передать задачу в разработку",
            risk_text="",
            jira_links=[],
            needs_review=False,
        )

        draft = build_daily_draft(
            target_date=self.target_date,
            notes=[note],
            projects=[self.project],
            default_manager_name="Анатолий Графкин",
            default_lead_name="Дмитрий Кононенко",
        )

        self.assertIn("<b>✅ Что сделано</b>", draft)
        self.assertIn("<b>🧭 План</b>", draft)
        # Empty risk section must NOT render a "- нет" filler line.
        self.assertNotIn("⚠️ Риски", draft)
        self.assertNotIn("- нет", draft)
        # Title gets the project emoji.
        self.assertIn("📌 <b>Caller ID</b>", draft)
        self.assertIn("<b>Статус:</b> В работе.", draft)
        # Bullets use the modern • marker.
        self.assertIn("• Завершили аналитику.", draft)

    def test_concise_style_limits_number_of_items(self) -> None:
        note = Note(
            id=1,
            note_date=self.target_date.isoformat(),
            user_id=100,
            source="text",
            raw_text="",
            project_id=1,
            manager_name="Анатолий Графкин",
            lead_name="Дмитрий Кононенко",
            epic="",
            status_text="",
            done_text="первый пункт\nвторой пункт\nтретий пункт",
            plan_text="первый план\nвторой план",
            risk_text="первый риск\nвторой риск",
            jira_links=[],
            needs_review=False,
        )

        draft = build_daily_draft(
            target_date=self.target_date,
            notes=[note],
            projects=[self.project],
            default_manager_name="Анатолий Графкин",
            default_lead_name="Дмитрий Кононенко",
            style="concise",
        )

        self.assertIn("• Первый пункт.", draft)
        self.assertIn("• Второй пункт.", draft)
        self.assertNotIn("• Третий пункт.", draft)
        self.assertIn("• Первый план.", draft)
        self.assertNotIn("• Второй план.", draft)
        self.assertIn("• Первый риск.", draft)
        self.assertNotIn("• Второй риск.", draft)

    def test_risk_focus_places_risk_before_plan(self) -> None:
        note = Note(
            id=1,
            note_date=self.target_date.isoformat(),
            user_id=100,
            source="text",
            raw_text="",
            project_id=1,
            manager_name="Анатолий Графкин",
            lead_name="Дмитрий Кононенко",
            epic="",
            status_text="",
            done_text="идет перенос серверов",
            plan_text="согласовать окно для ночных работ",
            risk_text="сжатые сроки по освобождению здания",
            jira_links=[],
            needs_review=False,
        )

        draft = build_daily_draft(
            target_date=self.target_date,
            notes=[note],
            projects=[self.project],
            default_manager_name="Анатолий Графкин",
            default_lead_name="Дмитрий Кононенко",
            style="risk_focus",
        )

        self.assertIn("<b>Статус:</b> Требует внимания.", draft)
        # In risk_focus the risk section comes before the plan section.
        self.assertLess(draft.index("<b>⚠️ Риски</b>"), draft.index("<b>🧭 План</b>"))

    def test_uses_explicit_status_from_note_when_present(self) -> None:
        note = Note(
            id=1,
            note_date=self.target_date.isoformat(),
            user_id=100,
            source="text",
            raw_text="",
            project_id=1,
            manager_name="Анатолий Графкин",
            lead_name="Дмитрий Кононенко",
            epic="",
            status_text="ретесты",
            done_text="согласовали новый статус блокировки карты",
            plan_text="получить ОС от УВ по отчетам",
            risk_text="ресурсы УВ направлены на тесты АБС",
            jira_links=[],
            needs_review=False,
        )

        draft = build_daily_draft(
            target_date=self.target_date,
            notes=[note],
            projects=[self.project],
            default_manager_name="Анатолий Графкин",
            default_lead_name="Дмитрий Кононенко",
        )

        self.assertIn("<b>Статус:</b> ретесты", draft)

    def test_team_examples_style_matches_team_like_format(self) -> None:
        note = Note(
            id=1,
            note_date=self.target_date.isoformat(),
            user_id=100,
            source="text",
            raw_text="",
            project_id=1,
            manager_name="Анатолий Графкин",
            lead_name="Дмитрий Кононенко",
            epic="",
            status_text="тестирование (L3 testing, Visa test-case)",
            done_text="передали заявку на назначение тест-инженера",
            plan_text="остался 1 кейс по L3 ATM\nпланируем завершить тест и передать на рассмотрение вендору",
            risk_text="нет",
            jira_links=["https://jira.example.com/browse/VISA-1"],
            needs_review=False,
        )

        draft = build_daily_draft(
            target_date=self.target_date,
            notes=[note],
            projects=[self.project],
            default_manager_name="Анатолий Графкин",
            default_lead_name="Дмитрий Кононенко",
            style="team_examples",
        )

        self.assertNotIn("<b>Общие апдейты</b>", draft)
        self.assertIn("<b>Дата:</b> 24.04.2026", draft)
        self.assertIn("<b>1. Caller ID</b> | <a href=", draft)
        self.assertIn("<b>Статус:</b> тестирование (L3 testing, Visa test-case)", draft)
        self.assertIn("<b>Что сделано:</b>", draft)
        self.assertIn("<b>Планы на завтра:</b>", draft)
        self.assertIn("<b>Риск:</b>", draft)


    # ── Step 27 / C — templates visibly affect draft output ─────────
    def _note_with_full_intent_mix(self) -> Note:
        return Note(
            id=1,
            note_date=self.target_date.isoformat(),
            user_id=100,
            source="text",
            raw_text="",
            project_id=1,
            manager_name="Анатолий Графкин",
            lead_name="Дмитрий Кононенко",
            epic="",
            status_text="",
            done_text=(
                "закрыли релиз 2.4\n"
                "решение — на MVP оставить voice\n"
                "вопрос — кто владелец справочника?"
            ),
            plan_text="завтра делаем демо\nдоделать топнав",
            risk_text=(
                "Telegram WebView может закэшировать ассеты\n"
                "блокер — нет доступа к Jira API"
            ),
            jira_links=[],
            needs_review=False,
        )

    def test_standard_and_executive_templates_produce_different_output(self) -> None:
        note = self._note_with_full_intent_mix()
        std = build_daily_draft(
            target_date=self.target_date, notes=[note], projects=[self.project],
            default_manager_name="Анатолий Графкин", default_lead_name="Дмитрий Кононенко",
            style="standard",
        )
        exe = build_daily_draft(
            target_date=self.target_date, notes=[note], projects=[self.project],
            default_manager_name="Анатолий Графкин", default_lead_name="Дмитрий Кононенко",
            style="risk_focus",
        )
        # Output must visibly differ between templates.
        self.assertNotEqual(std, exe)

    def test_concise_template_trims_and_emits_overflow_marker(self) -> None:
        note = Note(
            id=1, note_date=self.target_date.isoformat(), user_id=100,
            source="text", raw_text="", project_id=1,
            manager_name="Анатолий Графкин", lead_name="Дмитрий Кононенко",
            epic="", status_text="",
            done_text="один\nдва\nтри\nчетыре\nпять",
            plan_text="",
            risk_text="",
            jira_links=[],
            needs_review=False,
        )
        draft = build_daily_draft(
            target_date=self.target_date, notes=[note], projects=[self.project],
            default_manager_name="Анатолий Графкин", default_lead_name="Дмитрий Кононенко",
            style="concise",
        )
        # done section limited to 2 in concise mode + overflow marker.
        self.assertIn("• Один.", draft)
        self.assertIn("• Два.", draft)
        self.assertNotIn("• Три.", draft)
        self.assertIn("ещё", draft)

    def test_executive_template_puts_blockers_and_risks_before_done(self) -> None:
        note = self._note_with_full_intent_mix()
        draft = build_daily_draft(
            target_date=self.target_date, notes=[note], projects=[self.project],
            default_manager_name="Анатолий Графкин", default_lead_name="Дмитрий Кононенко",
            style="risk_focus",
        )
        idx_blocker = draft.find("⛔ Блокеры")
        idx_risk = draft.find("⚠️ Риски")
        idx_done = draft.find("✅ Что сделано")
        self.assertGreater(idx_blocker, -1)
        self.assertGreater(idx_risk, -1)
        self.assertGreater(idx_done, -1)
        self.assertLess(idx_blocker, idx_done)
        self.assertLess(idx_risk, idx_done)
        # Status verdict surfaces the warning.
        self.assertIn("<b>Статус:</b> Требует внимания.", draft)


if __name__ == "__main__":
    unittest.main()
