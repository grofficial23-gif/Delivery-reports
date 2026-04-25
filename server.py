"""Render-friendly production entry point.

Runs the FastAPI Mini App server on the Render-assigned port and integrates
Telegram bot polling directly into the ASGI lifespan, solving conflict issues.
"""
from __future__ import annotations

import os
import sys
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

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from delivery_reports.web_app import build_web_app

def main() -> None:
    settings = load_settings()
    # Resolve db path so it handles correctly in any directory
    db_path = Path(settings.db_path)
    if not db_path.is_absolute():
        db_path = ROOT_DIR / db_path
    
    db = Database(db_path)
    repository = Repository(db)
    repository.ensure_default_project(
        settings.default_manager_name, settings.default_lead_name
    )
    repository.ensure_default_report_templates()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        transcription = TranscriptionService(
            mode=settings.transcribe_mode,
            whisper_model=settings.whisper_model,
        )
        tg_app = build_app(settings=settings, repository=repository, transcription=transcription)
        
        # Stop any pending or existing webhooks cleanly
        await tg_app.bot.delete_webhook(drop_pending_updates=True)
        await tg_app.initialize()
        await tg_app.start()
        # Start polling in the background without blocking the web loop
        await tg_app.updater.start_polling(drop_pending_updates=True)
        
        # Store tg_app in app.state if web_app needs to access it (e.g. for sending messages)
        app.state.bot_app = tg_app
        
        yield
        
        # Graceful shutdown
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()

    web_app = build_web_app(settings, repository)
    web_app.router.lifespan_context = lifespan

    port = int(os.environ.get("PORT", "10000"))
    print(f"Starting Unified Server (Web on port {port} + Bot Polling)...")
    uvicorn.run(
        web_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*"
    )

if __name__ == "__main__":
    main()
