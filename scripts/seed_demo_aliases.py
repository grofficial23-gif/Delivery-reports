"""Seed/refresh demo project aliases (idempotent, no destructive changes).

Usage:
    python -m scripts.seed_demo_aliases <owner_user_id>

Examples:
    python -m scripts.seed_demo_aliases 123456789

This script is safe to run multiple times. It only ever calls
``upsert_project`` which:
  - keeps existing manager_name / lead_name / jira_base_url unchanged,
  - replaces aliases_json with the merged superset of existing + new
    aliases.
It never deletes a project, never touches notes/drafts/payments, and
never modifies the schema.

The aliases below correspond to demo projects used in the tomorrow's
recording.  For your own projects, edit DEMO_PROJECTS below or call
``upsert_project`` directly from the admin Telegram bot menu.
"""
from __future__ import annotations

import sys
from typing import Iterable

from delivery_reports.config import load_settings
from delivery_reports.db import Database
from delivery_reports.repository import Project, Repository


# Edit this list for your own demo / production projects.  Each entry:
#   {
#       "name":              str — exact canonical project name
#       "aliases":           list[str] — alternative spellings
#       "manager_name":      str (optional) — override only when project
#                                              doesn't already have one
#       "lead_name":         str (optional) — same
#       "is_special_control": bool — flag for top-of-report section
#   }
DEMO_PROJECTS: list[dict[str, object]] = [
    {
        "name": "Delivery Reports",
        "aliases": ["Delivery", "PM Digest", "PM-Digest", "PMDigest", "DR"],
        "is_special_control": False,
    },
    {
        "name": "Bank Dashboard",
        "aliases": ["Bank", "Bank-Dashboard", "BankDash", "BD"],
        "is_special_control": False,
    },
    {
        "name": "Внедрение категорийного кэшбэка (BONUS-2055)",
        "aliases": [
            "BONUS-2055",
            "BONUS",
            "Кэшбэк",
            "Категорийный кэшбэк",
            "MCC",
            "ГТС",
            "МФС",
            "Антифрод",
        ],
        "is_special_control": True,
    },
]


def _merge_aliases(existing: Iterable[str], new: Iterable[str]) -> list[str]:
    merged: dict[str, str] = {}
    for alias in (*existing, *new):
        cleaned = (alias or "").strip()
        if not cleaned:
            continue
        merged.setdefault(cleaned.lower(), cleaned)
    return sorted(merged.values(), key=str.casefold)


def seed(owner_user_id: int) -> list[Project]:
    settings = load_settings()
    repository = Repository(Database(settings.db_path))
    repository.ensure_default_project(
        manager_name=settings.default_manager_name,
        lead_name=settings.default_lead_name,
        owner_user_id=owner_user_id,
    )
    existing = {p.name: p for p in repository.list_projects(owner_user_id=owner_user_id)}
    seeded: list[Project] = []
    for cfg in DEMO_PROJECTS:
        name = str(cfg["name"]).strip()
        new_aliases = list(cfg.get("aliases") or [])
        is_special = bool(cfg.get("is_special_control", False))
        prior = existing.get(name)
        prior_aliases = prior.aliases if prior else []
        merged = _merge_aliases(prior_aliases, new_aliases)
        manager_name = (prior.manager_name if prior else "") or settings.default_manager_name
        lead_name = (prior.lead_name if prior else "") or settings.default_lead_name
        jira_base_url = prior.jira_base_url if prior else ""
        project = repository.upsert_project(
            name=name,
            manager_name=manager_name,
            lead_name=lead_name,
            jira_base_url=jira_base_url,
            aliases=merged,
            is_special_control=is_special,
            owner_user_id=owner_user_id,
        )
        seeded.append(project)
        print(f"  • {project.name} → aliases: {', '.join(project.aliases) or '(none)'}")
    return seeded


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1
    try:
        owner_user_id = int(argv[1])
    except ValueError:
        print(f"Invalid owner_user_id: {argv[1]!r} — expected a Telegram user id (int).")
        return 2
    print(f"Seeding demo projects for owner_user_id={owner_user_id}…")
    seeded = seed(owner_user_id)
    print(f"OK: {len(seeded)} project(s) ensured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
