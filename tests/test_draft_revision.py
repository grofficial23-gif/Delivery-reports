from __future__ import annotations

import unittest

from delivery_reports.services.draft_revision import parse_revision_instruction


class DraftRevisionTests(unittest.TestCase):
    def test_parses_concise_instruction(self) -> None:
        request = parse_revision_instruction("Сделай короче")
        self.assertIsNotNone(request)
        self.assertEqual(request.style, "concise")

    def test_parses_risk_instruction(self) -> None:
        request = parse_revision_instruction("нужен акцент на риск")
        self.assertIsNotNone(request)
        self.assertEqual(request.style, "risk_focus")

    def test_parses_standard_instruction(self) -> None:
        request = parse_revision_instruction("обычный")
        self.assertIsNotNone(request)
        self.assertEqual(request.style, "standard")

    def test_parses_team_instruction(self) -> None:
        request = parse_revision_instruction("сделай командный")
        self.assertIsNotNone(request)
        self.assertEqual(request.style, "team_examples")

    def test_returns_none_for_unknown_instruction(self) -> None:
        self.assertIsNone(parse_revision_instruction("переведи на английский"))


if __name__ == "__main__":
    unittest.main()
