from __future__ import annotations

from datetime import date

from ..config import Settings
from ..repository import Repository
from .draft_builder import build_daily_draft


def build_and_store_daily_draft(
    repository: Repository,
    settings: Settings,
    target_date: date,
    user_id: int,
    style: str,
) -> str:
    user = repository.get_user(user_id)
    header_manager = settings.default_manager_name
    header_lead = settings.default_lead_name
    if user is not None:
        header_manager = (
            user.default_manager_name
            or user.display_name
            or user.telegram_full_name
            or settings.default_manager_name
        )
        header_lead = user.default_lead_name or settings.default_lead_name
    content = build_daily_draft(
        target_date=target_date,
        notes=repository.list_notes_for_user_on_date(user_id, target_date),
        projects=repository.list_projects(owner_user_id=user_id),
        default_manager_name=header_manager,
        default_lead_name=header_lead,
        style=style,
    )
    repository.save_draft(target_date, content, owner_user_id=user_id)
    return content


def finalize_daily_report(
    repository: Repository,
    target_date: date,
    content: str,
    author_user_id: int,
    style: str,
) -> None:
    footer = "\n\n<i>Сгенерировано в @igest_bot — Твои отчеты за 1 минуту</i>"
    if footer not in content:
        content += footer

    repository.save_final_report(
        target_date=target_date,
        content=content,
        source_draft_id=None,
        author_user_id=author_user_id,
        language=language,
        style=style,
    )
