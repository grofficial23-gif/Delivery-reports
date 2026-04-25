from __future__ import annotations

import argparse
import json
from pathlib import Path

from telegram.error import InvalidToken, NetworkError, TelegramError

from .bot_app import build_app
from .config import load_settings
from .db import Database
from .repository import Repository
from .services.jira_import import import_jira_csv
from .services.transcription import TranscriptionService


def seed_projects_if_available(repository: Repository, seed_path: Path) -> None:
    if not seed_path.exists():
        return
    with seed_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    for item in data:
        repository.upsert_project(
            name=item.get("name", "").strip() or "Без названия",
            manager_name=item.get("manager_name", "").strip(),
            lead_name=item.get("lead_name", "").strip(),
            jira_base_url=item.get("jira_base_url", "").strip(),
            aliases=item.get("aliases", []),
            is_special_control=bool(item.get("is_special_control", False)),
        )


def run() -> None:
    args = _parse_args()
    settings = load_settings()
    db = Database(settings.db_path)
    repository = Repository(db)
    repository.ensure_default_project(settings.default_manager_name, settings.default_lead_name)
    repository.ensure_default_report_templates()

    seed_projects_if_available(repository, Path("data/projects.sample.json"))
    if args.command == "import-jira":
        _run_jira_import(repository, Path(args.csv_path), args.jira_base_url or "")
        return
    if args.command == "web":
        _run_web_app(settings, repository)
        return

    transcription = TranscriptionService(
        mode=settings.transcribe_mode,
        whisper_model=settings.whisper_model,
    )
    app = build_app(settings=settings, repository=repository, transcription=transcription)
    try:
        app.run_polling()
    except InvalidToken as error:
        raise SystemExit(
            "Telegram bot token is invalid. Check TELEGRAM_BOT_TOKEN in .env and try again."
        ) from error
    except NetworkError as error:
        raise SystemExit(
            "Cannot reach Telegram API. Check internet access, DNS/VPN/proxy settings, and that api.telegram.org is reachable."
        ) from error
    except TelegramError as error:
        raise SystemExit(f"Telegram startup failed: {error}") from error


def _run_jira_import(repository: Repository, csv_path: Path, jira_base_url: str) -> None:
    issues, result = import_jira_csv(csv_path=csv_path, jira_base_url=jira_base_url)
    repository.replace_jira_issues(issues)
    synced_epics = repository.sync_epics_from_jira()
    print(f"Imported Jira issues: {result.imported_count}")
    print(f"Synced epics from Jira: {synced_epics}")
    if result.project_keys:
        print(f"Project keys: {', '.join(result.project_keys)}")


def _run_web_app(settings, repository: Repository) -> None:
    import uvicorn
    from .web_app import build_web_app

    app = build_web_app(settings=settings, repository=repository)
    uvicorn.run(app, host=settings.web_host, port=settings.web_port)


def _parse_args():
    parser = argparse.ArgumentParser(description="Delivery Reports bot")
    subparsers = parser.add_subparsers(dest="command")

    import_parser = subparsers.add_parser("import-jira", help="Import Jira issues from CSV")
    import_parser.add_argument("csv_path", help="Path to exported Jira CSV file")
    import_parser.add_argument("--jira-base-url", default="", help="Base Jira URL, example: https://jira.company.com")
    subparsers.add_parser("web", help="Run local web UI")

    return parser.parse_args()


if __name__ == "__main__":
    run()
