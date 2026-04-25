from __future__ import annotations

import argparse
import json
from pathlib import Path
import os

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
    
    ROOT_DIR = Path(__file__).resolve().parent.parent.parent
    db_path = Path(settings.db_path)
    if not db_path.is_absolute():
        db_path = ROOT_DIR / db_path

    db = Database(db_path)
    repository = Repository(db)
    repository.ensure_default_project(settings.default_manager_name, settings.default_lead_name)
    repository.ensure_default_report_templates()

    seed_projects_if_available(repository, Path("data/projects.sample.json"))
    if args.command == "import-jira":
        _run_jira_import(repository, Path(args.csv_path), args.jira_base_url or "")
        return
    transcription = TranscriptionService(
        mode=settings.transcribe_mode,
        whisper_model=settings.whisper_model,
    )
    tg_app = build_app(settings=settings, repository=repository, transcription=transcription)

    import uvicorn
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from .web_app import build_web_app

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Drop webhook and pending updates to fix telegram.error.Conflict on Render
        await tg_app.bot.delete_webhook(drop_pending_updates=True)
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
        yield
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()

    web_app = build_web_app(settings=settings, repository=repository)
    web_app.router.lifespan_context = lifespan

    port = int(os.environ.get("PORT", settings.web_port))
    uvicorn.run(web_app, host="0.0.0.0", port=port)


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
