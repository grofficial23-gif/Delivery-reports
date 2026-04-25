import pytest
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from delivery_reports.bot_app import send_daily_draft_job
from delivery_reports.config import Settings
from delivery_reports.db import Database
from delivery_reports.repository import Repository

class MockBot:
    def __init__(self):
        self.sent_messages = []
        
    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.sent_messages.append({"chat_id": chat_id, "text": text})

class MockApplication:
    def __init__(self, bot_data):
        self.bot_data = bot_data

class MockContext:
    def __init__(self, repository, settings):
        self.bot = MockBot()
        self.application = MockApplication({
            "repository": repository,
            "settings": settings
        })

@pytest.fixture
def settings():
    return Settings(
        telegram_bot_token="fake",
        owner_user_id=123,
        timezone="Asia/Bishkek"
    )

@pytest.fixture
def test_db_path():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir) / "test_cron.db"

@pytest.fixture
def repository(test_db_path):
    db = Database(test_db_path)
    repo = Repository(db)
    repo.ensure_default_report_templates()
    return repo

@pytest.mark.asyncio
async def test_send_daily_draft_job_weekdays(repository, settings, test_db_path):
    # Create the owner user
    conn = sqlite3.connect(test_db_path)
    conn.execute(
        "INSERT INTO users (telegram_user_id, display_name, created_at) VALUES (?, ?, datetime('now'))", 
        (123, "Owner User")
    )
    conn.commit()
    conn.close()

    ctx = MockContext(repository, settings)

    # Mock datetime to a Monday
    with patch("delivery_reports.bot_app.datetime") as mock_dt:
        # 2026-04-20 is a Monday
        mock_dt.now.return_value = datetime(2026, 4, 20)
        
        await send_daily_draft_job(ctx)
        
        assert len(ctx.bot.sent_messages) == 1
        assert "Owner User" in ctx.bot.sent_messages[0]["text"] or "Черновик отчета" in ctx.bot.sent_messages[0]["text"]

@pytest.mark.asyncio
async def test_send_daily_draft_job_weekends(repository, settings, test_db_path):
    # Create the owner user
    conn = sqlite3.connect(test_db_path)
    conn.execute(
        "INSERT INTO users (telegram_user_id, display_name, created_at) VALUES (?, ?, datetime('now'))", 
        (123, "Owner User")
    )
    conn.commit()
    conn.close()

    ctx = MockContext(repository, settings)

    # Mock datetime to a Saturday
    with patch("delivery_reports.bot_app.datetime") as mock_dt:
        # 2026-04-25 is a Saturday
        mock_dt.now.return_value = datetime(2026, 4, 25)
        
        await send_daily_draft_job(ctx)
        
        # Should not send on weekends
        assert len(ctx.bot.sent_messages) == 0
