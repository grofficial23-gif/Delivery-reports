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
from delivery_reports.services import note_capture
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
        yield settings, repo, project, client


def test_dump_extract_returns_404_when_flag_off(monkeypatch):
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
        r = client.post("/api/notes/dump_extract", json={"raw_text": "1234567890"})
        assert r.status_code == 404
        assert r.json()["error"] == "chat_dump_disabled"


def test_dump_save_returns_404_when_flag_off(monkeypatch):
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
        repo.upsert_user(42, "pm", "PM")
        client = TestClient(build_web_app(settings, repo), base_url="https://testserver")
        client.cookies.set(SESSION_COOKIE_NAME, issue_session_token(42, settings.web_session_secret))
        r = client.post(
            "/api/notes/dump_save",
            json={"items": [{"client_id": "a", "type": "done", "text": "hello world", "project_id": None}]},
        )
        assert r.status_code == 404
        assert r.json()["error"] == "chat_dump_disabled"


def test_dump_extract_too_short(dump_web_env):
    _settings, _repo, _project, client = dump_web_env
    r = client.post("/api/notes/dump_extract", json={"raw_text": "short"})
    assert r.status_code == 400
    assert r.json()["error"] == "too_short"


def test_dump_extract_no_api_key_returns_422(dump_web_env, monkeypatch):
    _settings, _repo, _project, client = dump_web_env
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
    _settings, repo, _project, client = dump_web_env
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
    _settings, _repo, _project, client = dump_web_env

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


def test_dump_save_requires_auth(monkeypatch):
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
        repo.upsert_user(42, "pm", "PM")
        client = TestClient(build_web_app(settings, repo), base_url="https://testserver")
        r = client.post(
            "/api/notes/dump_save",
            json={
                "items": [
                    {"client_id": "tmp_1", "type": "done", "text": "hello world", "project_id": None},
                ]
            },
        )
        assert r.status_code == 401
        assert r.json()["error"] == "auth_required"


def test_dump_save_creates_updates_via_existing_capture_function(dump_web_env, monkeypatch):
    _settings, repo, project, client = dump_web_env
    calls: list[str] = []
    real_store = note_capture.store_notes

    def tracing_store(*args: object, **kwargs: object):
        if len(args) >= 5:
            calls.append(str(args[4]))
        elif "source" in kwargs:
            calls.append(str(kwargs["source"]))
        return real_store(*args, **kwargs)

    monkeypatch.setattr("delivery_reports.web_app.capture_notes", tracing_store)
    n0 = _notes_count(repo)
    r = client.post(
        "/api/notes/dump_save",
        json={
            "items": [
                {
                    "client_id": "tmp_1",
                    "type": "done",
                    "text": "Закрыли API авторизации",
                    "project_id": project.id,
                },
            ]
        },
    )
    assert r.status_code == 200
    assert calls == ["chat_dump"]
    assert _notes_count(repo) == n0 + 1
    nid = r.json()["created"][0]["update_id"]
    assert repo.get_note(nid).source == "chat_dump"


def test_dump_save_handles_null_project_as_inbox(dump_web_env):
    _settings, repo, _project, client = dump_web_env
    n0 = _notes_count(repo)
    r = client.post(
        "/api/notes/dump_save",
        json={
            "items": [
                {
                    "client_id": "tmp_inbox",
                    "type": "risk",
                    "text": "Подрядчик не подтвердил доставку",
                    "project_id": None,
                },
            ]
        },
    )
    assert r.status_code == 200
    assert _notes_count(repo) == n0 + 1
    note = repo.get_note(r.json()["created"][0]["update_id"])
    assert note.project_id is None
    assert note.needs_review is True
    assert "Риск:" in (note.raw_text or "") or "Риск:" in (note.risk_text or "")


def test_dump_save_preserves_client_id_mapping(dump_web_env):
    _settings, repo, project, client = dump_web_env
    r = client.post(
        "/api/notes/dump_save",
        json={
            "items": [
                {"client_id": "tmp_second", "type": "plan", "text": "Second line", "project_id": project.id},
                {"client_id": "tmp_first", "type": "done", "text": "First line", "project_id": None},
            ]
        },
    )
    assert r.status_code == 200
    created = r.json()["created"]
    assert created[0]["client_id"] == "tmp_second"
    assert created[1]["client_id"] == "tmp_first"
    n_second = repo.get_note(created[0]["update_id"])
    n_first = repo.get_note(created[1]["update_id"])
    assert "План:" in (n_second.raw_text or "") or "План:" in (n_second.plan_text or "")
    assert n_first.project_id is None
    assert n_second.project_id == project.id


def test_dump_save_rejects_unknown_project_id(dump_web_env):
    _settings, repo, _project, client = dump_web_env
    n0 = _notes_count(repo)
    r = client.post(
        "/api/notes/dump_save",
        json={
            "items": [
                {"client_id": "tmp_1", "type": "done", "text": "hello world xx", "project_id": 99999},
            ]
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "unknown_project"
    assert _notes_count(repo) == n0


def test_dump_save_rejects_empty_items(dump_web_env):
    _settings, _repo, _project, client = dump_web_env
    r = client.post("/api/notes/dump_save", json={"items": []})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_items"


def test_dump_save_only_saves_submitted_items(dump_web_env):
    _settings, repo, project, client = dump_web_env
    n0 = _notes_count(repo)
    r = client.post(
        "/api/notes/dump_save",
        json={
            "items": [
                {"client_id": "tmp_1", "type": "note", "text": "only this one", "project_id": project.id},
            ]
        },
    )
    assert r.status_code == 200
    assert len(r.json()["created"]) == 1
    assert _notes_count(repo) == n0 + 1
