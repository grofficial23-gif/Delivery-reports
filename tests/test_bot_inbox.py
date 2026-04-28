"""Step 28C — bot /inbox command renders human-readable copy and a Mini App button."""
from __future__ import annotations

import sys
import tempfile
import types
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# python-telegram-bot's update/inlinekeyboard are heavy to construct in unit
# tests; we wrap the relevant calls with simple mocks instead. The test
# directly invokes cmd_inbox to validate the message text and the optional
# Mini App button payload.

from delivery_reports.config import Settings
from delivery_reports.db import Database
from delivery_reports.repository import NewNote, Repository
from delivery_reports import bot_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        telegram_bot_token="fake-token",
        owner_user_id=42,
        timezone="Asia/Bishkek",
        db_path=tmp_path / "bot_inbox.db",
        public_web_app_url="https://mini.example.com",
    )


@pytest.fixture
def repository(settings):
    repo = Repository(Database(settings.db_path))
    repo.ensure_default_project(
        manager_name=settings.default_manager_name,
        lead_name=settings.default_lead_name,
        owner_user_id=42,
    )
    return repo


@pytest.fixture
def context(repository, settings):
    ctx = MagicMock()
    ctx.application.bot_data = {"repository": repository, "settings": settings}
    ctx.args = []
    return ctx


def _make_update(user_id: int = 42):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "grafkin"
    update.effective_user.full_name = "Анатолий Графкин"
    update.message.reply_text = AsyncMock()
    return update


def _seed_unresolved(repository, raw_text: str) -> int:
    return repository.add_note(
        NewNote(
            note_date=date.today().isoformat(),
            user_id=42,
            source="bot",
            raw_text=raw_text,
            manager_name="Анатолий Графкин",
            lead_name="Дмитрий Кононенко",
            needs_review=True,
        )
    )


@pytest.mark.asyncio
async def test_inbox_command_uses_friendly_copy_and_advanced_fallback(repository, context):
    note_id = _seed_unresolved(repository, "обсуждали что-то общее")
    assert isinstance(note_id, int)

    update = _make_update()
    await bot_app.cmd_inbox(update, context)

    calls = update.message.reply_text.await_args_list
    assert calls, "cmd_inbox should send at least one message"
    main_text = calls[0].args[0] if calls[0].args else calls[0].kwargs.get("text", "")
    # Friendly Mini App-first guidance.
    assert "📲" in main_text
    assert "откройте Mini App" in main_text
    assert "Заметки без проекта" in main_text
    assert "выберите проект" in main_text
    # Old technical hint must be gone.
    assert "Resolve: <code>разобрать" not in main_text
    # Manual command preserved but labeled as advanced.
    assert "Для ручной команды" in main_text
    assert "/inbox resolve 15 DC701" in main_text


@pytest.mark.asyncio
async def test_inbox_command_appends_mini_app_button(repository, context):
    _seed_unresolved(repository, "ещё одна inbox-заметка")

    update = _make_update()
    await bot_app.cmd_inbox(update, context)

    calls = update.message.reply_text.await_args_list
    # Two sends: the inbox list, then the Mini App button follow-up.
    assert len(calls) == 2
    follow_up = calls[1]
    text = follow_up.args[0] if follow_up.args else follow_up.kwargs.get("text", "")
    assert "Mini App" in text
    markup = follow_up.kwargs.get("reply_markup")
    assert markup is not None, "Mini App follow-up must carry an inline keyboard"
    # First button must use a WebApp / Mini App URL.
    button = markup.inline_keyboard[0][0]
    assert button.web_app is not None
    assert button.web_app.url.startswith("https://mini.example.com")
    assert "Разобрать" in button.text


@pytest.mark.asyncio
async def test_inbox_command_skips_mini_app_button_when_url_missing(repository, settings, context):
    # Public Mini App URL not configured (e.g., local dev without HTTPS).
    import dataclasses
    settings_no_url = dataclasses.replace(settings, public_web_app_url="")
    context.application.bot_data["settings"] = settings_no_url
    _seed_unresolved(repository, "ещё одна inbox-заметка")

    update = _make_update()
    await bot_app.cmd_inbox(update, context)

    calls = update.message.reply_text.await_args_list
    # Only the main inbox list, no Mini App follow-up.
    assert len(calls) == 1
