"""Regression tests from real-world daily report shapes (Step 35).

Fixture source: ``tests/fixtures/report_examples.txt`` (representative extracts
in the style of «Примеры шаблона.txt»).
"""
from __future__ import annotations

import re
import unittest
from datetime import date
from pathlib import Path

from delivery_reports.repository import Note, Project
from delivery_reports.services.draft_builder import build_daily_draft
from delivery_reports.services.parsing import parse_note_blocks

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "report_examples.txt"
_TARGET = date(2026, 5, 1)
_JIRA = "https://jira.example.com"


def _projects() -> list[Project]:
    return [
        Project(1, 100, "Visa Principal", "M", "L", _JIRA, ["Visa", "VP"], False),
        Project(2, 100, "PAMS", "M", "L", _JIRA, ["PAMS"], False),
        Project(3, 100, "О!Афиша", "M", "L", _JIRA, ["O!Афиша"], False),
        Project(
            4,
            100,
            "Внедрение категорийного кэшбэка (BONUS-2055)",
            "M",
            "L",
            _JIRA,
            ["BONUS-2055", "BONUS", "кешбэк"],
            True,
        ),
        Project(5, 100, "MCC-словарь", "M", "L", _JIRA, ["MCC-словарь"], False),
        Project(6, 100, "Тен Арина", "M", "L", _JIRA, ["Тен Арина"], False),
        Project(7, 100, "Caller ID", "M", "L", _JIRA, ["Caller ID", "CallerID"], False),
        Project(8, 100, "DC701", "M", "L", _JIRA, ["DC701", "DEVOPS", "OM", "CREDITCOND"], False),
        Project(9, 100, "MRZ Reader", "M", "L", _JIRA, ["MRZ Reader", "MRZ"], False),
        Project(10, 100, "MyID", "M", "L", _JIRA, ["MyID", "SDK MyID"], False),
    ]


def load_example_map() -> dict[str, str]:
    raw = _FIXTURE.read_text(encoding="utf-8")
    pattern = re.compile(r"---BEGIN ([a-z0-9_]+)---\s*(.*?)\s*---END---", re.DOTALL | re.IGNORECASE)
    found = {m.group(1).lower(): m.group(2).strip() for m in pattern.finditer(raw)}
    if len(found) < 10:
        raise RuntimeError(f"expected >=10 examples in fixture, got {len(found)}")
    return found


def notes_from_example(body: str, projects: list[Project]) -> list[Note]:
    blocks = parse_note_blocks(body, projects)
    notes: list[Note] = []
    for i, block in enumerate(blocks, start=1):
        p = block.parsed
        notes.append(
            Note(
                id=i,
                note_date=_TARGET.isoformat(),
                user_id=100,
                source="text",
                raw_text=block.raw_text,
                project_id=p.project_id,
                manager_name="M",
                lead_name="L",
                epic=p.epic,
                status_text=p.status_text,
                done_text=p.done_text,
                plan_text=p.plan_text,
                risk_text=p.risk_text,
                jira_links=p.jira_links,
                needs_review=p.needs_review,
            )
        )
    return notes


class RealReportExamplesRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.examples = load_example_map()
        cls.projects = _projects()

    def test_real_examples_do_not_crash(self) -> None:
        for name, body in self.examples.items():
            with self.subTest(example=name):
                notes = notes_from_example(body, self.projects)
                draft = build_daily_draft(
                    _TARGET, notes, self.projects, "M", "L", style="standard"
                )
                self.assertTrue(draft.strip(), f"empty draft for {name}")

    def test_no_risk_when_risk_absent_or_none(self) -> None:
        keys = (
            "visa_principal",
            "pams_no_risk",
            "mrz_no_risk",
            "chat_noise_fyi",
            "meerim_multi_jira",
        )
        for key in keys:
            with self.subTest(example=key):
                body = self.examples[key]
                notes = notes_from_example(body, self.projects)
                draft = build_daily_draft(_TARGET, notes, self.projects, "M", "L")
                self.assertNotIn("⚠️ Риски", draft, msg=draft[:800])

    def test_explicit_risks_remain_risks(self) -> None:
        checks = (
            ("o_afisha_risk", "таймаут"),
            ("o_afisha_risk", "Сжатые сроки"),
            ("caller_id_explicit_risks", "малым объемом RAM"),
            ("caller_id_explicit_risks", "оператора"),
            ("bonus_mcc_block", "Зависим от скорости"),
            ("dc701_migration", "Сжатые сроки"),
        )
        for key, needle in checks:
            with self.subTest(example=key, needle=needle):
                notes = notes_from_example(self.examples[key], self.projects)
                draft = build_daily_draft(_TARGET, notes, self.projects, "M", "L")
                self.assertIn("⚠️ Риски", draft)
                self.assertIn(needle, draft)

    def test_problem_section_not_always_risk(self) -> None:
        notes = notes_from_example(self.examples["ten_arina_problem_blocker"], self.projects)
        draft = build_daily_draft(_TARGET, notes, self.projects, "M", "L")
        self.assertNotIn("⚠️ Риски", draft)
        self.assertIn("⛔ Блокеры", draft)
        self.assertIn("Android", draft)

    def test_blocker_is_blocker(self) -> None:
        notes = notes_from_example(self.examples["dc701_migration"], self.projects)
        draft = build_daily_draft(_TARGET, notes, self.projects, "M", "L")
        self.assertIn("⛔ Блокеры", draft)
        self.assertIn("консоли", draft.lower())

    def test_multi_project_message_separate_sections(self) -> None:
        notes = notes_from_example(self.examples["meerim_multi_jira"], self.projects)
        draft = build_daily_draft(_TARGET, notes, self.projects, "M", "L")
        self.assertGreaterEqual(draft.count("📌 <b>"), 3)
        self.assertIn("DC701", draft)
        self.assertIn("Caller ID", draft)
        self.assertIn("BONUS-2055", draft)

    def test_jira_codes_preserved(self) -> None:
        notes = notes_from_example(self.examples["meerim_multi_jira"], self.projects)
        draft = build_daily_draft(_TARGET, notes, self.projects, "M", "L")
        combine = notes_from_example(self.examples["bonus_mcc_block"], self.projects)
        notes2 = combine
        draft2 = build_daily_draft(_TARGET, notes2, self.projects, "M", "L")
        full = draft + "\n" + draft2
        for key in ("OM-37505", "CREDITCOND-2889", "DEVOPS-1642", "BONUS-2055"):
            with self.subTest(key=key):
                self.assertIn(key, full)

    def test_no_duplicate_bullets_across_sections(self) -> None:
        projects = self.projects
        pid = 8  # DC701
        note = Note(
            id=1,
            note_date=_TARGET.isoformat(),
            user_id=100,
            source="text",
            raw_text="",
            project_id=pid,
            manager_name="M",
            lead_name="L",
            epic="",
            status_text="",
            done_text="Один и тот же пункт для дедупа.\n",
            plan_text="",
            risk_text="Риск: Один и тот же пункт для дедупа.\n",
            jira_links=[],
            needs_review=False,
        )
        draft = build_daily_draft(_TARGET, [note], projects, "M", "L")
        self.assertEqual(draft.count("Один и тот же пункт для дедупа"), 1)

    def test_template_outputs_differ_and_risk_focus_order(self) -> None:
        notes = notes_from_example(self.examples["risk_focus_fixture"], self.projects)
        std = build_daily_draft(_TARGET, notes, self.projects, "M", "L", style="standard")
        concise = build_daily_draft(_TARGET, notes, self.projects, "M", "L", style="concise")
        risk_f = build_daily_draft(_TARGET, notes, self.projects, "M", "L", style="risk_focus")
        self.assertNotEqual(std, concise)
        self.assertNotEqual(std, risk_f)
        r_risk = risk_f.index("⚠️ Риски")
        r_done = risk_f.index("✅ Что сделано")
        self.assertLess(r_risk, r_done)

    def test_assistant_markdown_meta_stripped(self) -> None:
        body = self.examples["assistant_myid_markdown"]
        notes = notes_from_example(body, self.projects)
        draft = build_daily_draft(_TARGET, notes, self.projects, "M", "L")
        lower = draft.lower()
        self.assertNotIn("Вот готовый", draft)
        self.assertNotIn("> *", draft)
        self.assertNotIn("**", draft)
        self.assertNotIn("Дмитрий", draft)
        self.assertNotIn("Такой текст сразу", draft)
        self.assertNotIn("⚠️ Риски", draft)
        self.assertIn("MyID", draft)
        self.assertIn("720", draft)
        self.assertIn("не будем", lower)
        self.assertIn("запросим", lower)
        self.assertIn("вендор", lower)
        self.assertIn("◆ Решение", draft)
        self.assertIn("🧭 План", draft)


if __name__ == "__main__":
    unittest.main()
