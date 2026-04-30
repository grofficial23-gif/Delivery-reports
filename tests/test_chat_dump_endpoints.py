from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient
import pytest

from delivery_reports.chat_dump import extractor as chat_extractor
from delivery_reports.config import Settings
from delivery_reports.db import Database
from delivery_reports.repository import NewNote, Repository
from delivery_reports.services.mini_app_auth import issue_session_token
from delivery_reports.web_app import SESSION_COOKIE_NAME, build_web_app


def _notes_count(repo: Repository) -> int:
    with repo.db.connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0])


@pytest.fixture
def dump_web_env(monkeypatch):
    monkeypatch.setenv("ENABLE_CHAT_DUMP", "true")
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
        client.cookies.set(
            SESSION_COOKIE_NAME,
            issue_session_token(user.telegram_user_id, settings.web_session_secret),
        )
        yield settings, repo, client


def test_dump_endpoints_disabled_returns_404(monkeypatch):
    monkeypatch.setenv("ENABLE_CHAT_DUMP", "false")
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
        client = TestClient(build_web_app(settings, repo), base_url="https://testserver")
        r1 = client.post("/api/notes/dump_extract", json={"raw_text": "1234567890"})
        r2 = client.post("/api/notes/dump_save", json={})
        assert r1.status_code == 404
        assert r2.status_code == 404
        assert r1.json()["error"] == "chat_dump_disabled"
        assert r2.json()["error"] == "chat_dump_disabled"


def test_dump_extract_too_short(dump_web_env):
    _settings, _repo, client = dump_web_env
    r = client.post("/api/notes/dump_extract", json={"raw_text": "short"})
    assert r.status_code == 400
    assert r.json()["error"] == "too_short"


def test_dump_extract_no_api_key_returns_422(dump_web_env, monkeypatch):
    _settings, _repo, client = dump_web_env
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = client.post(
        "/api/notes/dump_extract",
        json={"raw_text": "1234567890 enough chars"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "llm_unavailable"
    assert body["reason"] == "no_api_key"


def test_dump_extract_does_not_write_db(dump_web_env, monkeypatch):
    _settings, repo, client = dump_web_env
    n0 = _notes_count(repo)

    def fake_extract(_cleaned: str, user_lang: str = "ru", **kwargs):
        return chat_extractor.ExtractionResult(
            facts=[
                chat_extractor.ExtractedFact(
                    client_id="tmp_1",
                    type="done",
                    text="x",
                    confidence=1.0,
                    project_hint=None,
                    suggested_project_id=None,
                )
            ],
            skipped=[],
            warnings=[],
            used_llm=True,
            fallback_reason=None,
        )

    monkeypatch.setattr(chat_extractor, "extract_facts", fake_extract)
    r = client.post("/api/notes/dump_extract", json={"raw_text": "1234567890"})
    assert r.status_code == 200
    assert _notes_count(repo) == n0


def test_dump_extract_mocked_success_includes_client_id(dump_web_env, monkeypatch):
    _settings, _repo, client = dump_web_env

    def fake_extract(_cleaned: str, user_lang: str = "ru", **kwargs):
        return chat_extractor.ExtractionResult(
            facts=[
                chat_extractor.ExtractedFact(
                    client_id="tmp_1",
                    type="done",
                    text="Shipped feature",
                    confidence=0.95,
                    project_hint="Demo",
                    suggested_project_id=None,
                )
            ],
            skipped=[chat_extractor.SkippedFragment("noise", "hi")],
            warnings=[],
            used_llm=True,
            fallback_reason=None,
        )

    monkeypatch.setattr(chat_extractor, "extract_facts", fake_extract)
    r = client.post(
        "/api/notes/dump_extract",
        json={"raw_text": "1234567890123"},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["extracted"][0]["client_id"] == "tmp_1"
    assert payload["extracted"][0]["type"] == "done"
    assert payload["extracted"][0]["text"] == "Shipped feature"
    assert payload["skipped"][0]["reason"] == "noise"


def test_dump_save_enabled_returns_501(dump_web_env):
    _settings, _repo, client = dump_web_env
    r = client.post("/api/notes/dump_save", json={})
    assert r.status_code == 501
    assert r.json()["error"] == "not_implemented"
