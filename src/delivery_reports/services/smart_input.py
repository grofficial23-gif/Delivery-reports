from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SmartInputAction:
    kind: str
    text: str = ""
    task_id: int | None = None
    project_name: str = ""


TASK_STATUS_PATTERNS = [
    ("task_done", re.compile(r"^(?:готово|сделано|done)\s+#?(\d+)\s*$", re.IGNORECASE)),
    ("task_waiting", re.compile(r"^(?:жду|waiting|wait)\s+#?(\d+)\s*$", re.IGNORECASE)),
    ("task_progress", re.compile(r"^(?:в работе|progress|in progress)\s+#?(\d+)\s*$", re.IGNORECASE)),
    ("task_open", re.compile(r"^(?:открыть|open)\s+#?(\d+)\s*$", re.IGNORECASE)),
]

INBOX_RESOLVE_RE = re.compile(r"^(?:разобрать|resolve)\s+(\d+)\s+(.+)$", re.IGNORECASE)
TASK_ADD_RE = re.compile(r"^(?:задача|task)\s*:\s*(.+)$", re.IGNORECASE)


def parse_smart_input(text: str) -> SmartInputAction | None:
    normalized = " ".join(text.strip().split())
    lowered = normalized.lower()
    if not lowered:
        return None

    if lowered in {"статус", "status", "что у меня", "сводка", "что уже добавлено", "статус дня"}:
        return SmartInputAction(kind="status")
    if lowered in {"мои задачи", "mytasks", "задачи", "tasks"}:
        return SmartInputAction(kind="mytasks")
    if lowered in {"inbox", "инбокс", "неразобранное", "неразобранные"}:
        return SmartInputAction(kind="inbox")
    if lowered in {"черновик", "покажи черновик", "show draft"}:
        return SmartInputAction(kind="show_draft")
    if lowered in {"финальный", "покажи финальный", "show final"}:
        return SmartInputAction(kind="show_final")

    task_match = TASK_ADD_RE.match(normalized)
    if task_match:
        return SmartInputAction(kind="add_task", text=task_match.group(1).strip())

    inbox_match = INBOX_RESOLVE_RE.match(normalized)
    if inbox_match:
        return SmartInputAction(
            kind="resolve_inbox",
            task_id=int(inbox_match.group(1)),
            project_name=inbox_match.group(2).strip(),
        )

    for kind, pattern in TASK_STATUS_PATTERNS:
        match = pattern.match(normalized)
        if match:
            return SmartInputAction(kind=kind, task_id=int(match.group(1)))

    return None
