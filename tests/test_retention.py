import pytest
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

from delivery_reports.bot_app import retention_campaign_job
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
    def __init__(self, repository):
        self.bot = MockBot()
        self.application = MockApplication({"repository": repository})

@pytest.fixture
def test_db_path():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir) / "test_retention.db"

@pytest.fixture
def repository(test_db_path):
    db = Database(test_db_path)
    # the schema is created on __init__
    return Repository(db)

@pytest.mark.asyncio
async def test_retention_campaign_sends_onboarding_and_upsell(repository, test_db_path):
    # Setup mock users directly via sqlite3 to bypass complex abstractions
    conn = sqlite3.connect(test_db_path)
    newbie_id = 999333  # User registered 2 days ago, no notes
    expiring_id = 999444  # User whose PRO expires in 3 days
    
    # Rule 1: User registered 2 days ago, NO notes
    conn.execute(
        "INSERT INTO users (telegram_user_id, display_name, created_at) VALUES (?, ?, datetime('now', '-2 days'))", 
        (newbie_id, "Newbie")
    )
    
    # Rule 2: User whose subscription expires in 3 days
    conn.execute(
        "INSERT INTO users (telegram_user_id, display_name, created_at) VALUES (?, ?, datetime('now', '-10 days'))", 
        (expiring_id, "Expiring User")
    )
    conn.execute(
        "INSERT INTO subscriptions (user_id, plan, expires_at) VALUES (?, 'pro', date('now', '+3 days'))", 
        (expiring_id,)
    )
    conn.commit()
    conn.close()

    # Run cron job
    ctx = MockContext(repository)
    await retention_campaign_job(ctx)
    
    # Assertions
    onboarding_sent = any(msg["chat_id"] == newbie_id and "Завал с проектами" in msg["text"] for msg in ctx.bot.sent_messages)
    renewal_sent = any(msg["chat_id"] == expiring_id and "истекает через 3 дня" in msg["text"] for msg in ctx.bot.sent_messages)

    assert onboarding_sent, "Onboarding message should be sent to new user without notes."
    assert renewal_sent, "Renewal warning should be sent to user with expiring PRO subscription."
