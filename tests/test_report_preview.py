from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from delivery_reports.config import Settings
from delivery_reports.db import Database
from delivery_reports.repository import NewNote, Repository
from delivery_reports.services.mini_app_auth import issue_session_token
from delivery_reports.web_app import SESSION_COOKIE_NAME, build_web_app


@pytest.fixture
def preview_env(tmp_path):
    settings = Settings(
        telegram_bot_token="test-token",
        owner_user_id=42,
        timezone="Asia/Bishkek",
        db_path=tmp_path / "preview.db",
        web_session_secret="preview-secret",
        dashboard_ui_version="v2",
    )
    repo = Repository(Database(settings.db_path))
    repo.ensure_default_report_templates()
    repo.upsert_user(42, "grafkin", "Анатолий Графкин")
    with repo.db.connect() as conn:
        conn.execute("ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT ''")
        conn.execute("UPDATE users SET timezone = ? WHERE telegram_user_id = ?", ("UTC", 42))
    client = TestClient(build_web_app(settings, repo), base_url="https://testserver")
    token = issue_session_token(42, settings.web_session_secret)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    return settings, repo, client


def _project(repo: Repository, name: str):
    return repo.upsert_project(
        name=name,
        manager_name="PM",
        lead_name="Lead",
        jira_base_url="",
        aliases=[],
        is_special_control=False,
        owner_user_id=42,
    )


def _note(repo: Repository, *, text: str, note_date: str = "2026-04-30", project_id: int | None = None, done: str = "", plan: str = "", risk: str = "", needs_review: bool = False) -> int:
    return repo.add_note(
        NewNote(
            note_date=note_date,
            user_id=42,
            source="test",
            raw_text=text,
            project_id=project_id,
            done_text=done,
            plan_text=plan,
            risk_text=risk,
            needs_review=needs_review,
        )
    )


def test_preview_empty_day_returns_empty_warning(preview_env):
    _, _, client = preview_env

    resp = client.get("/api/report/preview?date=2026-04-30")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_updates"] == 0
    assert data["warnings"] == ["empty_day"]
    assert data["projects"] == []


def test_preview_groups_updates_by_project(preview_env):
    _, repo, client = preview_env
    alpha = _project(repo, "Project A")
    beta = _project(repo, "Project B")
    for idx in range(3):
        _note(repo, text=f"A done {idx}", project_id=alpha.id, done=f"A done {idx}")
    for idx in range(2):
        _note(repo, text=f"B plan {idx}", project_id=beta.id, plan=f"B plan {idx}")
    _note(repo, text="Inbox item", needs_review=True)

    data = client.get("/api/report/preview?date=2026-04-30").json()

    assert data["total_updates"] == 6
    assert len(data["projects"]) == 2
    counts = {project["name"]: project["count"] for project in data["projects"]}
    assert counts == {"Project A": 3, "Project B": 2}
    assert data["inbox"]["count"] == 1


def test_preview_inbox_count_excludes_from_projects(preview_env):
    _, repo, client = preview_env
    _note(repo, text="No project", project_id=None, needs_review=True)

    data = client.get("/api/report/preview?date=2026-04-30").json()

    assert data["projects"] == []
    assert data["inbox"]["count"] == 1


def test_preview_text_short_truncated_to_80(preview_env):
    _, repo, client = preview_env
    project = _project(repo, "Project A")
    _note(repo, text="А" * 200, project_id=project.id, done="done")

    item = client.get("/api/report/preview?date=2026-04-30").json()["projects"][0]["items"][0]

    assert len(item["text_short"]) <= 83
    assert item["text_short"].endswith("…")


def test_preview_marks_possible_duplicate_within_project(preview_env):
    _, repo, client = preview_env
    project = _project(repo, "Project A")
    first_id = _note(repo, text="Закрыл API авторизации", project_id=project.id, done="Закрыл API авторизации")
    _note(repo, text="Закрыл апи авторизации", project_id=project.id, done="Закрыл апи авторизации")

    items = client.get("/api/report/preview?date=2026-04-30").json()["projects"][0]["items"]

    assert items[0]["possible_duplicate_of"] is None
    assert items[1]["possible_duplicate_of"] == first_id


def test_preview_does_not_mark_duplicates_across_projects(preview_env):
    _, repo, client = preview_env
    alpha = _project(repo, "Project A")
    beta = _project(repo, "Project B")
    _note(repo, text="Закрыл API", project_id=alpha.id, done="Закрыл API")
    _note(repo, text="Закрыл API", project_id=beta.id, done="Закрыл API")

    data = client.get("/api/report/preview?date=2026-04-30").json()

    for project in data["projects"]:
        assert project["items"][0]["possible_duplicate_of"] is None


def test_preview_does_not_mark_duplicates_in_inbox(preview_env):
    _, repo, client = preview_env
    _note(repo, text="Созвон с клиентом", needs_review=True)
    _note(repo, text="Созвон с клиентом", needs_review=True)

    items = client.get("/api/report/preview?date=2026-04-30").json()["inbox"]["items"]

    assert all("possible_duplicate_of" not in item or item["possible_duplicate_of"] is None for item in items)


def test_preview_uses_user_timezone_for_default_date(preview_env, monkeypatch):
    _, repo, client = preview_env
    with repo.db.connect() as conn:
        conn.execute("UPDATE users SET timezone = ? WHERE telegram_user_id = ?", ("Europe/Moscow", 42))
    monkeypatch.setattr(
        "delivery_reports.web_app._utcnow",
        lambda: datetime(2026, 4, 30, 22, 30, tzinfo=timezone.utc),
    )

    data = client.get("/api/report/preview").json()

    assert data["date"] == "2026-05-01"
    assert data["user_timezone"] == "Europe/Moscow"


def test_preview_returns_timezone_missing_warning(preview_env):
    _, repo, client = preview_env
    with repo.db.connect() as conn:
        conn.execute("UPDATE users SET timezone = '' WHERE telegram_user_id = ?", (42,))

    data = client.get("/api/report/preview?date=2026-04-30").json()

    assert "timezone_missing" in data["warnings"]
    assert data["user_timezone"] == "UTC"


def test_preview_does_not_modify_database(preview_env):
    _, repo, client = preview_env
    project = _project(repo, "Project A")
    _note(repo, text="Done", project_id=project.id, done="Done")
    before = _table_counts(repo)

    resp = client.get("/api/report/preview?date=2026-04-30")

    assert resp.status_code == 200
    assert _table_counts(repo) == before


def _table_counts(repo: Repository) -> dict[str, int]:
    with repo.db.connect() as conn:
        tables = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        return {
            table: int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
            for table in tables
        }
