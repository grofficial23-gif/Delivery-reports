"""Render-friendly production entry point.

Runs the FastAPI Mini App server on the Render-assigned port so the platform
sees an active web service and serves the UI, while Telegram bot polling continues in parallel.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path



ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from delivery_reports.bot_app import build_app
from delivery_reports.config import load_settings
from delivery_reports.db import Database
from delivery_reports.repository import Repository
from delivery_reports.services.transcription import TranscriptionService


def _run_http_server(settings, repository) -> None:
    import uvicorn
    from delivery_reports.web_app import build_web_app

    port = int(os.environ.get("PORT", "10000"))
    app = build_web_app(settings, repository)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*"
    )


def main() -> None:
    settings = load_settings()
    db = Database(settings.db_path)
    repository = Repository(db)
    repository.ensure_default_project(
        settings.default_manager_name, settings.default_lead_name
    )
    repository.ensure_default_report_templates()

    web_thread = threading.Thread(target=_run_http_server, args=(settings, repository), daemon=True)
    web_thread.start()
    print(f"HTTP server started on port {os.environ.get('PORT', '10000')}")

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
