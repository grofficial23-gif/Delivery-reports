from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL,
    manager_name TEXT DEFAULT '',
    lead_name TEXT DEFAULT '',
    jira_base_url TEXT DEFAULT '',
    aliases_json TEXT NOT NULL DEFAULT '[]',
    is_special_control INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner_user_id, name)
);

CREATE TABLE IF NOT EXISTS users (
    telegram_user_id INTEGER PRIMARY KEY,
    telegram_username TEXT DEFAULT '',
    telegram_full_name TEXT DEFAULT '',
    display_name TEXT DEFAULT '',
    default_manager_name TEXT DEFAULT '',
    default_lead_name TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS epics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'manual',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, name),
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note_date TEXT NOT NULL,
    user_id INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    transcript_text TEXT DEFAULT '',
    project_id INTEGER,
    manager_name TEXT DEFAULT '',
    lead_name TEXT DEFAULT '',
    epic TEXT DEFAULT '',
    status_text TEXT DEFAULT '',
    done_text TEXT DEFAULT '',
    plan_text TEXT DEFAULT '',
    risk_text TEXT DEFAULT '',
    jira_links_json TEXT NOT NULL DEFAULT '[]',
    needs_review INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS pm_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    owner_user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    project_id INTEGER,
    epic TEXT NOT NULL DEFAULT '',
    jira_key TEXT NOT NULL DEFAULT '',
    jira_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'normal',
    due_date TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual',
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    draft_date TEXT NOT NULL,
    owner_user_id INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS final_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    report_date TEXT NOT NULL,
    content TEXT NOT NULL,
    source_draft_id INTEGER,
    author_user_id INTEGER NOT NULL DEFAULT 0,
    language TEXT NOT NULL DEFAULT 'ru',
    style TEXT NOT NULL DEFAULT 'standard'
);

CREATE TABLE IF NOT EXISTS report_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    style TEXT NOT NULL DEFAULT 'standard',
    is_default INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jira_issues (
    issue_key TEXT PRIMARY KEY,
    summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT '',
    assignee TEXT NOT NULL DEFAULT '',
    reporter TEXT NOT NULL DEFAULT '',
    watcher_names TEXT NOT NULL DEFAULT '',
    updated_at_text TEXT NOT NULL DEFAULT '',
    project_name TEXT NOT NULL DEFAULT '',
    project_key TEXT NOT NULL DEFAULT '',
    issue_type TEXT NOT NULL DEFAULT '',
    epic_name TEXT NOT NULL DEFAULT '',
    labels_text TEXT NOT NULL DEFAULT '',
    issue_url TEXT NOT NULL DEFAULT '',
    raw_payload_json TEXT NOT NULL DEFAULT '{}',
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'active',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT DEFAULT NULL,
    payment_method TEXT NOT NULL DEFAULT 'none',
    payment_ref TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_pm_tasks_owner_status ON pm_tasks(owner_user_id, status);
CREATE INDEX IF NOT EXISTS idx_notes_user_date ON notes(user_id, note_date);
CREATE INDEX IF NOT EXISTS idx_final_reports_author_date ON final_reports(author_user_id, report_date);
"""


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            self._run_migrations(conn)

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        self._migrate_projects_to_user_scope(conn)
        self._ensure_column(conn, "notes", "user_id", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "notes", "manager_name", "TEXT DEFAULT ''")
        self._ensure_column(conn, "notes", "lead_name", "TEXT DEFAULT ''")
        self._ensure_column(conn, "notes", "status_text", "TEXT DEFAULT ''")
        self._ensure_column(conn, "drafts", "owner_user_id", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "pm_tasks", "epic", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "pm_tasks", "jira_key", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "pm_tasks", "jira_url", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "pm_tasks", "status", "TEXT NOT NULL DEFAULT 'open'")
        self._ensure_column(conn, "pm_tasks", "priority", "TEXT NOT NULL DEFAULT 'normal'")
        self._ensure_column(conn, "pm_tasks", "due_date", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "pm_tasks", "source", "TEXT NOT NULL DEFAULT 'manual'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_user_date ON notes(user_id, note_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_drafts_owner_date ON drafts(owner_user_id, draft_date)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_final_reports_author_date ON final_reports(author_user_id, report_date)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_owner_name ON projects(owner_user_id, name)")

    def _migrate_projects_to_user_scope(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("PRAGMA table_info(projects)").fetchall()
        existing_columns = {row["name"] for row in rows}
        if "owner_user_id" in existing_columns:
            return

        conn.executescript(
            """
            CREATE TABLE projects_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL,
                manager_name TEXT DEFAULT '',
                lead_name TEXT DEFAULT '',
                jira_base_url TEXT DEFAULT '',
                aliases_json TEXT NOT NULL DEFAULT '[]',
                is_special_control INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner_user_id, name)
            );

            INSERT INTO projects_v2(
                id, owner_user_id, name, manager_name, lead_name, jira_base_url,
                aliases_json, is_special_control, created_at
            )
            SELECT
                id,
                0,
                name,
                manager_name,
                lead_name,
                jira_base_url,
                aliases_json,
                is_special_control,
                created_at
            FROM projects;

            DROP TABLE projects;
            ALTER TABLE projects_v2 RENAME TO projects;
            """
        )

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing_columns = {row["name"] for row in rows}
        if column_name in existing_columns:
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
