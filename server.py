"""Combined entry point for production deployment.

Runs both the Telegram bot (polling) and the web server (uvicorn)
concurrently in a single process — ideal for Railway / Render / Fly.io.
"""
from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path

import uvicorn

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from delivery_reports.bot_app import build_app
from delivery_reports.config import load_settings
from delivery_reports.db import Database
from delivery_reports.repository import Repository
from delivery_reports.services.transcription import TranscriptionService
from delivery_reports.web_app import build_web_app


def main() -> None:
    settings = load_settings()
    db = Database(settings.db_path)
    repository = Repository(db)
    repository.ensure_default_project(
        settings.default_manager_name, settings.default_lead_name
    )
    repository.ensure_default_report_templates()

    # Build web app
    web_app = build_web_app(settings=settings, repository=repository)

    # Run uvicorn in a background thread
    web_host = settings.web_host
    web_port = settings.web_port

    config = uvicorn.Config(
        web_app,
        host=web_host,
        port=web_port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    web_thread = threading.Thread(target=server.run, daemon=True)
    web_thread.start()
    print(f"Web server started on http://{web_host}:{web_port}")

    # Build and run Telegram bot in main thread
    transcription = TranscriptionService(
        mode=settings.transcribe_mode,
        whisper_model=settings.whisper_model,
    )
    app = build_app(settings=settings, repository=repository, transcription=transcription)

    print("Starting Telegram bot polling...")
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    try:
        app.run_polling()
    finally:
        if not event_loop.is_closed():
            event_loop.close()


if __name__ == "__main__":
    main()
