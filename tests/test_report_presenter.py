from __future__ import annotations

import unittest

from delivery_reports.repository import Note
from delivery_reports.services.report_presenter import (
    build_note_preview,
    html_report_to_plain_text,
    split_telegram_chunks,
)


class ReportPresenterTests(unittest.TestCase):
    def test_html_report_to_plain_text_keeps_structure(self) -> None:
        html = (
            "<b>Дата:</b> 24.04.2026\n"
            "<b>1. DC701</b>\n"
            "<b>Что сделано:</b>\n"
            "- Перенесли серверы.\n"
            '<b>Jira:</b> <a href="https://jira.example.com/browse/DC-1">Jira 1</a>'
        )

        text = html_report_to_plain_text(html)

        self.assertIn("Дата: 24.04.2026", text)
        self.assertIn("1. DC701", text)
        self.assertIn("Jira 1 (https://jira.example.com/browse/DC-1)", text)

    def test_split_telegram_chunks_splits_long_text(self) -> None:
        long_text = ("Блок текста.\n" * 800).strip()

        chunks = split_telegram_chunks(long_text, max_length=500)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))

    def test_build_note_preview_prefers_structured_summary(self) -> None:
        note = Note(
            id=11,
            note_date="2026-04-24",
            user_id=42,
            source="mini_app",
            raw_text="Очень длинный исходный текст, который не должен попадать в preview как есть.",
            project_id=None,
            manager_name="Анатолий",
            lead_name="Дмитрий",
            epic="",
            status_text="в работе",
            done_text="согласовали окно ночных работ\nподтвердили список систем",
            plan_text="отправить на ревью",
            risk_text="ждем доступы",
            jira_links=[],
            needs_review=True,
        )

        preview = build_note_preview(note)

        self.assertIn("Статус: в работе", preview)
        self.assertIn("Сделано:", preview)
        self.assertIn("Дальше:", preview)
        self.assertIn("Блокеры:", preview)
        self.assertNotIn("Очень длинный исходный текст", preview)


if __name__ == "__main__":
    unittest.main()
