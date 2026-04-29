#!/usr/bin/env python3
"""Smoke: parse fixture examples and summarize draft stats (dev only).

Usage (from repo root)::

    python scripts/run_report_regression.py

Requires ``tests/fixtures/report_examples.txt``. Uses the same project list
as ``tests/test_real_report_examples._projects()``.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from delivery_reports.repository import Note, Project  # noqa: E402
from delivery_reports.services.draft_builder import build_daily_draft  # noqa: E402
from delivery_reports.services.parsing import parse_note_blocks  # noqa: E402

_FIXTURE = _REPO / "tests" / "fixtures" / "report_examples.txt"
_JIRA = "https://jira.example.com"
_TARGET = date(2026, 5, 1)


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


def load_examples() -> dict[str, str]:
    raw = _FIXTURE.read_text(encoding="utf-8")
    pat = re.compile(r"---BEGIN ([a-z0-9_]+)---\s*(.*?)\s*---END---", re.DOTALL | re.IGNORECASE)
    return {m.group(1).lower(): m.group(2).strip() for m in pat.finditer(raw)}


def main() -> int:
    if not _FIXTURE.is_file():
        print(f"Missing fixture: {_FIXTURE}", file=sys.stderr)
        return 1
    projects = _projects()
    examples = load_examples()
    warnings: list[str] = []
    risk_hits = 0
    blocker_hits = 0
    project_hits = 0

    for name, body in sorted(examples.items()):
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
        draft = build_daily_draft(_TARGET, notes, projects, "M", "L", style="standard")
        project_hits += draft.count("📌 <b>")
        project_hits += draft.count("📥 <b>")
        if "⚠️ Риски" in draft:
            risk_hits += 1
        if "⛔ Блокеры" in draft:
            blocker_hits += 1
        if not draft.strip():
            warnings.append(f"empty draft for {name}")
        if any(n.needs_review for n in notes):
            warnings.append(f"{name}: unresolved project on a block")

    print(f"Examples processed: {len(examples)}")
    print(f"Draft sections (📌/📥 headers, summed): {project_hits}")
    print(f"Examples with ⚠️ Риски section: {risk_hits}")
    print(f"Examples with ⛔ Блокеры section: {blocker_hits}")
    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("Warnings: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
