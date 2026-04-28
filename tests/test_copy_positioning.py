"""Step 30A — Copy-positioning tests: FREE=text-first, voice/AI gated to PRO.

Tests cover:
- Landing page no longer implies voice is a FREE/default feature.
- Landing page contains new FREE/PRO positioning line.
- Bot /start sends text-first welcome with PRO voice note.
"""
from __future__ import annotations

import dataclasses
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from delivery_reports.config import Settings
from delivery_reports.db import Database
from delivery_reports.repository import NewNote, Repository
from delivery_reports.web_app import build_web_app
from fastapi.testclient import TestClient
from delivery_reports import bot_app


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_settings(tmp_path):
    return Settings(
        telegram_bot_token="fake-tok",
        owner_user_id=42,
        timezone="Asia/Bishkek",
        db_path=tmp_path / "copy.db",
        public_web_app_url="https://mini.example.com",
        landing_ui_version="v2",
    )


@pytest.fixture
def repository(tmp_settings):
    repo = Repository(Database(tmp_settings.db_path))
    repo.ensure_default_report_templates()
    return repo


# ── Landing page copy ────────────────────────────────────────────────────────

class TestLandingCopyPositioning:
    def _landing_client(self, tmp_settings, repository):
        return TestClient(
            build_web_app(tmp_settings, repository),
            base_url="https://testserver",
        )

    def test_landing_no_longer_says_zametku_ili_golosovoe(self, tmp_settings, repository):
        client = self._landing_client(tmp_settings, repository)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "заметку или голосовое" not in resp.text.lower()
        assert "пришлите заметку или голосовое" not in resp.text.lower()

    def test_landing_contains_free_text_notes_positioning(self, tmp_settings, repository):
        client = self._landing_client(tmp_settings, repository)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "FREE: текстовые заметки" in resp.text
        assert "PRO" in resp.text

    def test_landing_hero_subtext_is_text_first(self, tmp_settings, repository):
        client = self._landing_client(tmp_settings, repository)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Пишите апдейты в течение дня" in resp.text

    def test_landing_voice_positioned_as_pro(self, tmp_settings, repository):
        client = self._landing_client(tmp_settings, repository)
        resp = client.get("/")
        assert resp.status_code == 200
        # Voice → text must now carry a PRO tag, not FREE.
        # Simplest check: "Voice" appears near "PRO" and not near "FREE".
        text = resp.text
        voice_idx = text.lower().find("voice → текст")
        assert voice_idx != -1, "Voice → текст card must exist"
        # Grab 200 chars after the card heading to find the tag.
        snippet = text[voice_idx : voice_idx + 400]
        assert "PRO" in snippet, "Voice card must be tagged PRO"
        assert ">FREE<" not in snippet, "Voice card must NOT be tagged FREE"

    def test_landing_step_01_does_not_mention_voice_as_default(self, tmp_settings, repository):
        client = self._landing_client(tmp_settings, repository)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Пишите апдейты текстом" in resp.text
        # Old copy gone.
        assert "Пишите или диктуете заметки" not in resp.text

    def test_landing_testimonial_uses_text_first_quote(self, tmp_settings, repository):
        client = self._landing_client(tmp_settings, repository)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "диктую голосовые заметки" not in resp.text
        assert "добавляю короткие апдейты" in resp.text

    def test_landing_why_not_chatgpt_section_present(self, tmp_settings, repository):
        client = self._landing_client(tmp_settings, repository)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "ChatGPT" in resp.text
        assert "контекст" in resp.text.lower()


# ── Bot /start copy ──────────────────────────────────────────────────────────

def _make_update_start(user_id: int = 42):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "grafkin"
    update.effective_user.full_name = "Анатолий Графкин"
    update.effective_chat.id = user_id
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def _make_context_start(repository, settings):
    ctx = MagicMock()
    ctx.application.bot_data = {"repository": repository, "settings": settings}
    ctx.args = []
    ctx.bot = MagicMock()
    ctx.bot.send_photo = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_start_message_is_text_first(tmp_settings, repository):
    repository.upsert_user(
        telegram_user_id=42,
        telegram_username="grafkin",
        telegram_full_name="Анатолий Графкин",
    )
    update = _make_update_start()
    context = _make_context_start(repository, tmp_settings)

    await bot_app.cmd_start(update, context)

    calls = update.message.reply_text.await_args_list
    assert calls, "/start must send at least one message"
    all_text = " ".join(
        (c.args[0] if c.args else c.kwargs.get("text", "")) for c in calls
    )
    # New text-first positioning.
    assert "текстом" in all_text.lower()
    assert "PRO" in all_text
    assert "Голосовые заметки" in all_text
    # Old heavy voice-only copy must be gone.
    assert "хаос из задач и созвонов" not in all_text
    assert "пишите апдейты по проектам" not in all_text.lower()
