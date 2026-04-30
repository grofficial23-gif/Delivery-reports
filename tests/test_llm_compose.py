from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient
import pytest

from delivery_reports.config import Settings
from delivery_reports.db import Database
from delivery_reports.llm.compose import smart_compose
from delivery_reports.llm.errors import LLMInvalidResponse
from delivery_reports.repository import NewNote, Repository
from delivery_reports.services.draft_builder import build_daily_draft
from delivery_reports.services.mini_app_auth import issue_session_token
from delivery_reports.web_app import SESSION_COOKIE_NAME, build_web_app


@dataclass
class FakeUpdate:
    id: int
    note_date: str = "2026-04-30"
    raw_text: str = "Закрыл API"
    project_id: int | None = 1
    done_text: str = "Закрыл API"
    plan_text: str = ""
    risk_text: str = ""


class FakeProvider:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {
            "kept": [
                {
                    "project_id": 1,
                    "type": "done",
                    "text": "Закрыл API",
                    "source_ids": [1],
                    "salience": 0.8,
                }
            ],
            "excluded": [],
        }
        self.error = error
        self.calls = []

    def complete_json(self, system_prompt, user_prompt, json_schema, max_output_tokens=2000, temperature=0.1):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "json_schema": json_schema,
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
            }
        )
        if self.error:
            raise self.error
        return self.payload


def test_compose_returns_feature_flag_off_when_disabled(monkeypatch):
    updates = [FakeUpdate(1), FakeUpdate(2, done_text="Собрал релиз", raw_text="Собрал релиз")]
    monkeypatch.setenv("ENABLE_LLM_COMPOSE", "false")

    result = smart_compose(updates, "standard")

    assert result.used_llm is False
    assert result.fallback_reason == "feature_flag_off"
    assert [item.source_ids for item in result.kept] == [[1], [2]]
    assert result.excluded == []


def test_compose_returns_no_api_key_fallback(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COMPOSE", "true")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = smart_compose([FakeUpdate(1)], "standard")

    assert result.used_llm is False
    assert result.fallback_reason == "no_api_key"
    assert result.excluded == []


def test_compose_uses_llm_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COMPOSE", "true")
    provider = FakeProvider(
        {
            "kept": [
                {
                    "project_id": 1,
                    "type": "done",
                    "text": "API логина готов",
                    "source_ids": [1, 2],
                    "salience": 0.8,
                }
            ],
            "excluded": [
                {"source_id": 2, "reason": "duplicate", "duplicate_of": 1, "note": "дубликат"}
            ],
        }
    )

    result = smart_compose([FakeUpdate(1), FakeUpdate(2)], "standard", provider=provider)

    assert result.used_llm is True
    assert result.kept[0].text == "API логина готов"
    assert result.excluded[0].reason == "duplicate"


def test_compose_falls_back_on_timeout(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COMPOSE", "true")
    result = smart_compose([FakeUpdate(1)], "standard", provider=FakeProvider(error=TimeoutError()))

    assert result.used_llm is False
    assert result.fallback_reason == "timeout"


def test_compose_falls_back_on_invalid_json(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COMPOSE", "true")
    result = smart_compose([FakeUpdate(1)], "standard", provider=FakeProvider(error=LLMInvalidResponse("bad")))

    assert result.used_llm is False
    assert result.fallback_reason == "invalid_json"


def test_compose_truncates_to_max_input(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COMPOSE", "true")
    monkeypatch.setenv("LLM_MAX_INPUT_UPDATES", "200")
    updates = [FakeUpdate(i) for i in range(1, 251)]
    kept = [
        {
            "project_id": 1,
            "type": "done",
            "text": "Закрыл API",
            "source_ids": [1],
            "salience": 0.7,
        }
    ]

    result = smart_compose(updates, "standard", provider=FakeProvider({"kept": kept, "excluded": []}))

    incomplete = [item for item in result.excluded if item.reason == "incomplete"]
    assert len(incomplete) == 50
    assert incomplete[0].source_id == 201


def test_compose_filters_invalid_source_ids(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COMPOSE", "true")
    provider = FakeProvider(
        {
            "kept": [
                {"project_id": 1, "type": "done", "text": "ok", "source_ids": [1], "salience": 0.5},
                {"project_id": 1, "type": "done", "text": "bad", "source_ids": [999], "salience": 0.5},
            ],
            "excluded": [
                {"source_id": 999, "reason": "low_signal", "duplicate_of": None, "note": None}
            ],
        }
    )

    result = smart_compose([FakeUpdate(1)], "standard", provider=provider)

    assert [item.text for item in result.kept] == ["ok"]
    assert result.excluded == []


def test_compose_passes_template_and_lang_in_prompt(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COMPOSE", "true")
    provider = FakeProvider()

    smart_compose([FakeUpdate(1, project_id=3)], "concise", user_lang="ru", provider=provider)

    prompt = provider.calls[0]["user_prompt"]
    assert "Шаблон: concise (Коротко)" in prompt
    assert "Язык: ru" in prompt
    assert '[Project 3]' in prompt


@pytest.fixture
def web_env(monkeypatch):
    monkeypatch.setenv("ENABLE_LLM_COMPOSE", "false")
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            telegram_bot_token="test-token",
            owner_user_id=42,
            timezone="UTC",
            db_path=Path(tmp) / "web.db",
            web_session_secret="secret",
        )
        repo = Repository(Database(settings.db_path))
        repo.ensure_default_report_templates()
        user = repo.upsert_user(42, "pm", "PM")
        project = repo.upsert_project(
            name="Delivery",
            manager_name="PM",
            lead_name="Lead",
            jira_base_url="",
            aliases=[],
            is_special_control=False,
            owner_user_id=42,
        )
        repo.add_note(
            NewNote(
                note_date=date.today().isoformat(),
                user_id=42,
                source="test",
                raw_text="Закрыл API",
                project_id=project.id,
                done_text="Закрыл API",
            )
        )
        client = TestClient(build_web_app(settings, repo), base_url="https://testserver")
        client.cookies.set(SESSION_COOKIE_NAME, issue_session_token(user.telegram_user_id, settings.web_session_secret))
        yield settings, repo, project, client


def test_report_endpoint_returns_excluded_and_used_llm_fields(web_env):
    _settings, _repo, _project, client = web_env

    response = client.post("/draft/build?format=json", headers={"accept": "application/json"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["excluded"] == []
    assert payload["used_llm"] is False
    assert payload["fallback_reason"] == "feature_flag_off"
    assert payload["text"]


def test_report_endpoint_existing_behavior_unchanged_with_flag_off(web_env):
    settings, repo, project, client = web_env
    notes = repo.list_notes_for_user_on_date(42, date.today())
    expected = build_daily_draft(
        target_date=date.today(),
        notes=notes,
        projects=[project],
        default_manager_name="PM",
        default_lead_name=settings.default_lead_name,
        style="standard",
    )

    response = client.post("/draft/build?format=json", headers={"accept": "application/json"})

    assert response.json()["text"] == expected
