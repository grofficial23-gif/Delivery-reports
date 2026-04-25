"""Shared constants, helpers, and utilities used across bot and web layers."""
from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .config import Settings


# Jira issue key pattern — single source of truth.
JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def task_status_label(value: str) -> str:
    """Human-readable label for PM task status."""
    mapping = {
        "open": "Открыта",
        "in_progress": "В работе",
        "waiting": "Ждет",
        "done": "Готово",
    }
    return mapping.get(value, value)


def today_date(settings: Settings) -> date:
    """Current date in the configured timezone."""
    return datetime.now(ZoneInfo(settings.timezone)).date()
