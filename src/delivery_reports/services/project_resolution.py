from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..repository import Project, Repository, UserProfile
from ..shared import JIRA_KEY_RE


@dataclass
class ProjectResolution:
    project_id: int | None
    candidate_project_ids: list[int]


def resolve_or_create_project(
    raw_name: str,
    repository: Repository,
    user: UserProfile,
    settings: Settings,
) -> tuple[Project, bool]:
    project = repository.find_project_by_name_or_alias(raw_name, owner_user_id=user.telegram_user_id)
    if project is not None:
        return project, False
    name = raw_name.strip()
    project = repository.upsert_project(
        name=name,
        manager_name=resolve_manager_name(None, user, settings),
        lead_name=resolve_lead_name(None, user, settings),
        jira_base_url="",
        aliases=[name],
        is_special_control=False,
        owner_user_id=user.telegram_user_id,
    )
    return project, True


def resolve_manager_name(project: Project | None, user: UserProfile, settings: Settings) -> str:
    return (
        (project.manager_name if project else "")
        or user.default_manager_name
        or user.display_name
        or user.telegram_full_name
        or settings.default_manager_name
    )


def resolve_lead_name(project: Project | None, user: UserProfile, settings: Settings) -> str:
    return (project.lead_name if project else "") or user.default_lead_name or settings.default_lead_name


def resolve_project_for_block(
    repository: Repository,
    block_text: str,
    parsed_note: Any,
    fallback_project_ids: list[int],
    owner_user_id: int | None = None,
) -> ProjectResolution:
    resolved_project_id = parsed_note.project_id
    candidate_ids = unique_ids(parsed_note.candidate_project_ids)

    if resolved_project_id is None:
        issue_project_ids = unique_ids(
            [
                repository.find_project_id_by_issue_key(issue_key, owner_user_id=owner_user_id) or 0
                for issue_key in extract_issue_keys(block_text)
            ]
        )
        issue_project_ids = [project_id for project_id in issue_project_ids if project_id]
        if len(issue_project_ids) == 1:
            resolved_project_id = issue_project_ids[0]
        candidate_ids = unique_ids(issue_project_ids + candidate_ids)

    if resolved_project_id is None and parsed_note.epic:
        epic_project_ids = repository.find_project_ids_by_epic(parsed_note.epic, owner_user_id=owner_user_id)
        if len(epic_project_ids) == 1:
            resolved_project_id = epic_project_ids[0]
        candidate_ids = unique_ids(epic_project_ids + candidate_ids)

    if resolved_project_id is not None:
        return ProjectResolution(
            project_id=resolved_project_id,
            candidate_project_ids=unique_ids([resolved_project_id] + candidate_ids),
        )
    if candidate_ids:
        return ProjectResolution(project_id=None, candidate_project_ids=candidate_ids)
    return ProjectResolution(project_id=None, candidate_project_ids=fallback_project_ids)


def project_names_by_ids(repository: Repository, project_ids: list[int], owner_user_id: int | None = None) -> list[str]:
    names: list[str] = []
    for project_id in project_ids:
        project = repository.get_project(project_id, owner_user_id=owner_user_id)
        if project is None:
            continue
        names.append(project.name)
    return names


def parse_project_definition(text: str) -> dict[str, object]:
    parts = [part.strip() for part in text.split("|") if part.strip()]
    payload: dict[str, object] = {
        "name": "",
        "aliases": [],
        "manager_name": "",
        "lead_name": "",
        "jira_base_url": "",
        "is_special_control": False,
        "has_special_control": False,
    }
    for index, part in enumerate(parts):
        if ":" not in part:
            if index == 0 and not payload["name"]:
                payload["name"] = part.strip()
            continue
        key, value = [chunk.strip() for chunk in part.split(":", 1)]
        key_lower = key.lower()
        if index == 0 and key_lower == "проект":
            payload["name"] = value
            continue
        if key_lower in {"алиасы", "алиас", "aliases"}:
            payload["aliases"] = [item.strip() for item in value.split(",") if item.strip()]
            continue
        if key_lower in {"менеджер", "manager"}:
            payload["manager_name"] = value
            continue
        if key_lower in {"руководитель", "lead"}:
            payload["lead_name"] = value
            continue
        if key_lower in {"jira", "jira_url"}:
            payload["jira_base_url"] = value
            continue
        if key_lower in {"контроль", "special", "особый контроль"}:
            payload["has_special_control"] = True
            payload["is_special_control"] = value.lower() in {"yes", "y", "да", "true", "1", "особый"}
    return payload


def parse_epic_definition(text: str) -> dict[str, object]:
    parts = [part.strip() for part in text.split("|") if part.strip()]
    payload: dict[str, object] = {
        "epic_name": "",
        "project_name": "",
        "aliases": [],
    }
    for index, part in enumerate(parts):
        if ":" not in part:
            continue
        key, value = [chunk.strip() for chunk in part.split(":", 1)]
        key_lower = key.lower()
        if index == 0 and key_lower == "эпик":
            payload["epic_name"] = value
            continue
        if key_lower == "проект":
            payload["project_name"] = value
            continue
        if key_lower in {"алиасы", "алиас", "aliases"}:
            payload["aliases"] = [item.strip() for item in value.split(",") if item.strip()]
            continue
    return payload


def fallback_project_ids(repository: Repository, owner_user_id: int | None = None) -> list[int]:
    ids: list[int] = []
    for project in repository.list_projects(owner_user_id=owner_user_id):
        if project.name.lower() == "без проекта":
            continue
        ids.append(project.id)
        if len(ids) == 4:
            break
    return ids


def looks_like_project_name(text: str) -> bool:
    return "\n" not in text and len(text.strip()) <= 60


def extract_issue_keys(text: str) -> list[str]:
    return [match.group(1).upper() for match in JIRA_KEY_RE.finditer(text)]


def unique_ids(values: list[int]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
