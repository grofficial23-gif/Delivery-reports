from __future__ import annotations

from csv import DictReader
from dataclasses import dataclass
from pathlib import Path

from ..repository import JiraIssue


@dataclass
class JiraImportResult:
    imported_count: int
    project_keys: list[str]


def import_jira_csv(csv_path: Path, jira_base_url: str = "") -> tuple[list[JiraIssue], JiraImportResult]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = DictReader(file)
        issues: list[JiraIssue] = []
        project_keys: set[str] = set()
        for row in reader:
            issue_key = _pick(row, "Issue key", "Key", "issue key", "issuekey", "key")
            if not issue_key:
                continue
            project_key = _pick(row, "Project key", "Project Key", "project key")
            project_name = _pick(row, "Project name", "Project Name", "project name", "Project")
            epic_name = _pick(
                row,
                "Epic Link Summary",
                "Epic Name",
                "Custom field (Epic Name)",
                "Epic",
                "Epic Link",
            )
            issue_url = _pick(row, "Issue URL", "URL", "Issue Url")
            if not issue_url and jira_base_url:
                issue_url = f"{jira_base_url.rstrip('/')}/browse/{issue_key}"

            issue = JiraIssue(
                issue_key=issue_key,
                summary=_pick(row, "Summary", "summary"),
                status=_pick(row, "Status", "status"),
                priority=_pick(row, "Priority", "priority"),
                assignee=_pick(row, "Assignee", "assignee"),
                reporter=_pick(row, "Reporter", "reporter"),
                watcher_names=_pick(row, "Watchers", "watchers"),
                updated_at_text=_pick(row, "Updated", "updated"),
                project_name=project_name,
                project_key=project_key,
                issue_type=_pick(row, "Issue Type", "Type", "issue type"),
                epic_name=epic_name,
                labels_text=_pick(row, "Labels", "labels"),
                issue_url=issue_url,
            )
            issues.append(issue)
            if project_key:
                project_keys.add(project_key)

    result = JiraImportResult(
        imported_count=len(issues),
        project_keys=sorted(project_keys),
    )
    return issues, result


def _pick(row: dict[str, str], *candidates: str) -> str:
    for candidate in candidates:
        if candidate in row and row[candidate]:
            return row[candidate].strip()
    for candidate in candidates:
        candidate_lower = candidate.lower()
        for key, value in row.items():
            if key and key.lower() == candidate_lower and value:
                return value.strip()
    return ""

