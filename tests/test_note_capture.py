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
                intent_kind="done",
            ),
            StoredNoteResult(
                note_id=2,
                project_name="Не уверен",
                manager_name="Анатолий",
                lead_name="Дмитрий",
                needs_review=True,
                candidate_names=["DC701", "НСП"],
                summary_line="нужна привязка проекта",
                intent_kind="plan",
            ),
        ]

        rendered = render_saved_notes_message(results)

        self.assertIn("<b>Сообщение разделил на 2 блока</b>", rendered)
        self.assertIn("<b>Последний неуточненный блок</b>", rendered)
        self.assertIn("<b>Варианты:</b> DC701, НСП", rendered)
        # Auto-split summary present for >=2 results.
        self.assertIn("Разобрано: 2 пункта", rendered)
        self.assertIn("1 сделано", rendered)
        self.assertIn("1 плана", rendered)

    def test_single_result_does_not_render_auto_split_summary(self) -> None:
        result = StoredNoteResult(
            note_id=1,
            project_name="DC701",
            manager_name="Анатолий",
            lead_name="Дмитрий",
            needs_review=False,
            candidate_names=[],
            summary_line="закрыли релиз",
            intent_kind="done",
        )

        rendered = render_saved_notes_message([result])

        self.assertNotIn("Разобрано:", rendered)


if __name__ == "__main__":
    unittest.main()
