from __future__ import annotations

import unittest

from delivery_reports.services.note_capture import (
    StoredNoteResult,
    render_saved_note_message,
    render_saved_notes_message,
)


class NoteCaptureRenderingTests(unittest.TestCase):
    def test_single_note_message_uses_html_sections_and_escapes_text(self) -> None:
        result = StoredNoteResult(
            note_id=1,
            project_name="DC701 <core>",
            manager_name="Анатолий",
            lead_name="Дмитрий",
            needs_review=True,
            candidate_names=["DC701", "DR"],
            summary_line="сделали <перенос>",
        )

        rendered = render_saved_note_message(result)

        self.assertIn("<b>Заметка сохранена</b>", rendered)
        self.assertIn("DC701 &lt;core&gt;", rendered)
        self.assertIn("сделали &lt;перенос&gt;", rendered)
        self.assertIn("<code>проект: Название</code>", rendered)

    def test_multiple_notes_message_highlights_last_unresolved_block(self) -> None:
        results = [
            StoredNoteResult(
                note_id=1,
                project_name="Caller ID",
                manager_name="Анатолий",
                lead_name="Дмитрий",
                needs_review=False,
                candidate_names=[],
                summary_line="аналитика готова",
            ),
            StoredNoteResult(
                note_id=2,
                project_name="Не уверен",
                manager_name="Анатолий",
                lead_name="Дмитрий",
                needs_review=True,
                candidate_names=["DC701", "НСП"],
                summary_line="нужна привязка проекта",
            ),
        ]

        rendered = render_saved_notes_message(results)

        self.assertIn("<b>Сообщение разделил на 2 блока</b>", rendered)
        self.assertIn("<b>Последний неуточненный блок</b>", rendered)
        self.assertIn("<b>Варианты:</b> DC701, НСП", rendered)


if __name__ == "__main__":
    unittest.main()
