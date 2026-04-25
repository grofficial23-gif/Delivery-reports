from __future__ import annotations

from ..repository import Repository


def template_state_key(user_id: int) -> str:
    return f"report_template:{user_id}"


def selected_template_key(repository: Repository, user_id: int) -> str:
    return (repository.get_state(template_state_key(user_id)) or "").strip().lower()


def set_selected_template_key(repository: Repository, user_id: int, template_key: str) -> None:
    repository.set_state(template_state_key(user_id), template_key.strip().lower())


def default_template_style(repository: Repository) -> str:
    template = repository.get_default_report_template()
    if template is None:
        return "standard"
    return template.style or "standard"


def resolve_style_for_user(repository: Repository, user_id: int) -> str:
    selected_key = selected_template_key(repository, user_id)
    if selected_key:
        template = repository.get_report_template(selected_key)
        if template is not None and template.is_active:
            return template.style or "standard"
    return default_template_style(repository)
