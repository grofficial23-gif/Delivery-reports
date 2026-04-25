from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json

from .db import Database


@dataclass
class Project:
    id: int
    owner_user_id: int
    name: str
    manager_name: str
    lead_name: str
    jira_base_url: str
    aliases: list[str]
    is_special_control: bool


@dataclass
class UserProfile:
    telegram_user_id: int
    telegram_username: str
    telegram_full_name: str
    display_name: str
    default_manager_name: str
    default_lead_name: str


@dataclass
class JiraIssue:
    issue_key: str
    summary: str
    status: str
    priority: str
    assignee: str
    reporter: str
    watcher_names: str
    updated_at_text: str
    project_name: str
    project_key: str
    issue_type: str
    epic_name: str
    labels_text: str
    issue_url: str


@dataclass
class Epic:
    id: int
    project_id: int
    name: str
    aliases: list[str]
    source: str
    is_active: bool


@dataclass
class Note:
    id: int
    note_date: str
    user_id: int
    source: str
    raw_text: str
    project_id: int | None
    manager_name: str
    lead_name: str
    epic: str
    status_text: str
    done_text: str
    plan_text: str
    risk_text: str
    jira_links: list[str] = field(default_factory=list)
    needs_review: bool = False


@dataclass
class NewNote:
    note_date: str
    user_id: int
    source: str
    raw_text: str
    transcript_text: str = ""
    project_id: int | None = None
    manager_name: str = ""
    lead_name: str = ""
    epic: str = ""
    status_text: str = ""
    done_text: str = ""
    plan_text: str = ""
    risk_text: str = ""
    jira_links: list[str] = field(default_factory=list)
    needs_review: bool = False


@dataclass
class ReportTemplate:
    template_key: str
    title: str
    description: str
    style: str
    is_default: bool
    is_active: bool


@dataclass
class PMTask:
    id: int
    owner_user_id: int
    title: str
    project_id: int | None
    epic: str
    jira_key: str
    jira_url: str
    status: str
    priority: str
    due_date: str
    source: str
    created_at: str
    updated_at: str


@dataclass
class NewPMTask:
    owner_user_id: int
    title: str
    project_id: int | None = None
    epic: str = ""
    jira_key: str = ""
    jira_url: str = ""
    status: str = "open"
    priority: str = "normal"
    due_date: str = ""
    source: str = "manual"


class Repository:
    def __init__(self, db: Database):
        self.db = db

    def list_projects(self, owner_user_id: int | None = None) -> list[Project]:
        with self.db.connect() as conn:
            if owner_user_id is None:
                rows = conn.execute(
                    """
                    SELECT id, owner_user_id, name, manager_name, lead_name, jira_base_url, aliases_json, is_special_control
                    FROM projects
                    ORDER BY name
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, owner_user_id, name, manager_name, lead_name, jira_base_url, aliases_json, is_special_control
                    FROM projects
                    WHERE owner_user_id = ?
                    ORDER BY name
                    """,
                    (owner_user_id,),
                ).fetchall()
        return [self._project_from_row(row) for row in rows]

    def get_project(self, project_id: int, owner_user_id: int | None = None) -> Project | None:
        with self.db.connect() as conn:
            if owner_user_id is None:
                row = conn.execute(
                    """
                    SELECT id, owner_user_id, name, manager_name, lead_name, jira_base_url, aliases_json, is_special_control
                    FROM projects
                    WHERE id = ?
                    """,
                    (project_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id, owner_user_id, name, manager_name, lead_name, jira_base_url, aliases_json, is_special_control
                    FROM projects
                    WHERE id = ? AND owner_user_id = ?
                    """,
                    (project_id, owner_user_id),
                ).fetchone()
        return self._project_from_row(row) if row else None

    def find_project_by_name_or_alias(self, value: str, owner_user_id: int | None = None) -> Project | None:
        value_clean = value.strip().lower()
        if not value_clean:
            return None
        projects = self.list_projects(owner_user_id=owner_user_id)
        for project in projects:
            if project.name.lower() == value_clean:
                return project
            aliases = {alias.strip().lower() for alias in project.aliases if alias.strip()}
            if value_clean in aliases:
                return project
        for project in projects:
            if value_clean in project.name.lower():
                return project
            aliases = {alias.strip().lower() for alias in project.aliases if alias.strip()}
            if any(value_clean in alias for alias in aliases):
                return project
        return None

    def ensure_default_project(self, manager_name: str, lead_name: str, owner_user_id: int = 0) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO projects(owner_user_id, name, manager_name, lead_name, aliases_json)
                VALUES(?, ?, ?, ?, ?)
                """,
                (owner_user_id, "Без проекта", manager_name, lead_name, "[]"),
            )

    def ensure_default_report_templates(self) -> None:
        defaults = [
            ("standard", "Баланс", "Обычный daily: баланс между сделанным, планом и рисками", "standard"),
            ("concise", "Только главное", "Сжатая версия, когда нужен максимально короткий текст", "concise"),
            ("risk_focus", "Для руководителя", "Сначала риски и блокеры, потом контекст", "risk_focus"),
            ("team", "Для команды", "Формат ближе к привычным daily reports команды", "team_examples"),
        ]
        with self.db.connect() as conn:
            for template_key, title, description, style in defaults:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO report_templates(
                        template_key, title, description, style, is_default, is_active
                    )
                    VALUES(?, ?, ?, ?, 0, 1)
                    """,
                    (template_key, title, description, style),
                )
                conn.execute(
                    """
                    UPDATE report_templates
                    SET title = ?, description = ?, style = ?, is_active = 1
                    WHERE template_key = ?
                    """,
                    (title, description, style, template_key),
                )
            default_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM report_templates WHERE is_default = 1"
            ).fetchone()
            if not default_count or int(default_count["cnt"]) == 0:
                conn.execute("UPDATE report_templates SET is_default = 0")
                conn.execute(
                    "UPDATE report_templates SET is_default = 1 WHERE template_key = ?",
                    ("standard",),
                )

    def list_report_templates(self, active_only: bool = True) -> list[ReportTemplate]:
        with self.db.connect() as conn:
            if active_only:
                rows = conn.execute(
                    """
                    SELECT template_key, title, description, style, is_default, is_active
                    FROM report_templates
                    WHERE is_active = 1
                    ORDER BY is_default DESC, template_key ASC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT template_key, title, description, style, is_default, is_active
                    FROM report_templates
                    ORDER BY is_default DESC, template_key ASC
                    """
                ).fetchall()
        return [self._template_from_row(row) for row in rows]

    def get_report_template(self, template_key: str) -> ReportTemplate | None:
        key = template_key.strip().lower()
        if not key:
            return None
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT template_key, title, description, style, is_default, is_active
                FROM report_templates
                WHERE template_key = ?
                LIMIT 1
                """,
                (key,),
            ).fetchone()
        return self._template_from_row(row) if row else None

    def get_default_report_template(self) -> ReportTemplate | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT template_key, title, description, style, is_default, is_active
                FROM report_templates
                WHERE is_active = 1
                ORDER BY is_default DESC, template_key ASC
                LIMIT 1
                """
            ).fetchone()
        return self._template_from_row(row) if row else None

    def set_default_report_template(self, template_key: str) -> bool:
        template = self.get_report_template(template_key)
        if template is None or not template.is_active:
            return False
        with self.db.connect() as conn:
            conn.execute("UPDATE report_templates SET is_default = 0")
            conn.execute(
                """
                UPDATE report_templates
                SET is_default = 1, updated_at = CURRENT_TIMESTAMP
                WHERE template_key = ?
                """,
                (template.template_key,),
            )
        return True

    def upsert_project(
        self,
        name: str,
        manager_name: str,
        lead_name: str,
        jira_base_url: str,
        aliases: list[str],
        is_special_control: bool,
        owner_user_id: int = 0,
    ) -> Project:
        aliases_json = json.dumps(sorted(set(a.strip() for a in aliases if a.strip())), ensure_ascii=False)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects(
                    owner_user_id, name, manager_name, lead_name, jira_base_url, aliases_json, is_special_control
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_user_id, name) DO UPDATE SET
                    manager_name=excluded.manager_name,
                    lead_name=excluded.lead_name,
                    jira_base_url=excluded.jira_base_url,
                    aliases_json=excluded.aliases_json,
                    is_special_control=excluded.is_special_control
                """,
                (
                    owner_user_id,
                    name.strip(),
                    manager_name.strip(),
                    lead_name.strip(),
                    jira_base_url.strip(),
                    aliases_json,
                    int(is_special_control),
                ),
            )
            row = conn.execute(
                """
                SELECT id, owner_user_id, name, manager_name, lead_name, jira_base_url, aliases_json, is_special_control
                FROM projects
                WHERE owner_user_id = ? AND name = ?
                """,
                (owner_user_id, name.strip()),
            ).fetchone()
        return self._project_from_row(row)

    def update_project_people(self, project_id: int, manager_name: str, lead_name: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE projects
                SET manager_name = ?, lead_name = ?
                WHERE id = ?
                """,
                (manager_name.strip(), lead_name.strip(), project_id),
            )

    def list_epics(self, project_id: int | None = None, owner_user_id: int | None = None) -> list[Epic]:
        with self.db.connect() as conn:
            if project_id is not None:
                rows = conn.execute(
                    """
                    SELECT epics.id, epics.project_id, epics.name, epics.aliases_json, epics.source, epics.is_active
                    FROM epics
                    JOIN projects ON projects.id = epics.project_id
                    WHERE epics.project_id = ?
                    ORDER BY epics.name
                    """,
                    (project_id,),
                ).fetchall()
            elif owner_user_id is None:
                rows = conn.execute(
                    """
                    SELECT id, project_id, name, aliases_json, source, is_active
                    FROM epics
                    ORDER BY name
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT epics.id, epics.project_id, epics.name, epics.aliases_json, epics.source, epics.is_active
                    FROM epics
                    JOIN projects ON projects.id = epics.project_id
                    WHERE projects.owner_user_id = ?
                    ORDER BY epics.name
                    """,
                    (owner_user_id,),
                ).fetchall()
        return [self._epic_from_row(row) for row in rows]

    def upsert_epic(
        self,
        project_id: int,
        name: str,
        aliases: list[str] | None = None,
        source: str = "manual",
    ) -> Epic | None:
        epic_name = name.strip()
        if not epic_name:
            return None
        alias_values = [epic_name]
        if aliases:
            alias_values.extend(aliases)
        aliases_json = json.dumps(sorted(set(item.strip() for item in alias_values if item.strip())), ensure_ascii=False)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO epics(project_id, name, aliases_json, source, is_active)
                VALUES(?, ?, ?, ?, 1)
                ON CONFLICT(project_id, name) DO UPDATE SET
                    aliases_json=excluded.aliases_json,
                    source=excluded.source,
                    is_active=1,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (project_id, epic_name, aliases_json, source),
            )
            row = conn.execute(
                """
                SELECT id, project_id, name, aliases_json, source, is_active
                FROM epics
                WHERE project_id = ? AND name = ?
                """,
                (project_id, epic_name),
            ).fetchone()
        return self._epic_from_row(row) if row else None

    def find_project_ids_by_epic(self, epic_name: str, owner_user_id: int | None = None) -> list[int]:
        value = epic_name.strip().lower()
        if not value:
            return []
        project_ids: list[int] = []
        for epic in self.list_epics(owner_user_id=owner_user_id):
            if epic.name.strip().lower() == value:
                project_ids.append(epic.project_id)
                continue
            alias_set = {alias.strip().lower() for alias in epic.aliases if alias.strip()}
            if value in alias_set:
                project_ids.append(epic.project_id)
        return sorted(set(project_ids))

    def find_project_id_by_issue_key(self, issue_key: str, owner_user_id: int | None = None) -> int | None:
        key = issue_key.strip().upper()
        if not key:
            return None
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT issue_key, summary, status, priority, assignee, reporter, watcher_names,
                       updated_at_text, project_name, project_key, issue_type, epic_name,
                       labels_text, issue_url
                FROM jira_issues
                WHERE UPPER(issue_key) = ?
                LIMIT 1
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        issue = self._jira_issue_from_row(row)
        project = self._match_project_for_issue(issue, owner_user_id=owner_user_id)
        return project.id if project else None

    def upsert_user(self, telegram_user_id: int, telegram_username: str, telegram_full_name: str) -> UserProfile:
        full_name = telegram_full_name.strip()
        username = telegram_username.strip()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO users(
                    telegram_user_id, telegram_username, telegram_full_name, display_name, default_manager_name
                )
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    telegram_username=excluded.telegram_username,
                    telegram_full_name=excluded.telegram_full_name,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (telegram_user_id, username, full_name, full_name, full_name),
            )
            row = conn.execute(
                """
                SELECT telegram_user_id, telegram_username, telegram_full_name, display_name,
                       default_manager_name, default_lead_name
                FROM users
                WHERE telegram_user_id = ?
                """,
                (telegram_user_id,),
            ).fetchone()
        return self._user_from_row(row)

    def get_user(self, telegram_user_id: int) -> UserProfile | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT telegram_user_id, telegram_username, telegram_full_name, display_name,
                       default_manager_name, default_lead_name
                FROM users
                WHERE telegram_user_id = ?
                """,
                (telegram_user_id,),
            ).fetchone()
        return self._user_from_row(row) if row else None

    def get_most_recent_user(self) -> UserProfile | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT telegram_user_id, telegram_username, telegram_full_name, display_name,
                       default_manager_name, default_lead_name
                FROM users
                ORDER BY updated_at DESC, created_at DESC, telegram_user_id DESC
                LIMIT 1
                """
            ).fetchone()
        return self._user_from_row(row) if row else None

    def update_user_defaults(
        self,
        telegram_user_id: int,
        display_name: str | None = None,
        default_manager_name: str | None = None,
        default_lead_name: str | None = None,
    ) -> UserProfile:
        user = self.get_user(telegram_user_id)
        if user is None:
            raise ValueError("User not found")
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET display_name = ?,
                    default_manager_name = ?,
                    default_lead_name = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ?
                """,
                (
                    (display_name if display_name is not None else user.display_name).strip(),
                    (default_manager_name if default_manager_name is not None else user.default_manager_name).strip(),
                    (default_lead_name if default_lead_name is not None else user.default_lead_name).strip(),
                    telegram_user_id,
                ),
            )
        updated = self.get_user(telegram_user_id)
        if updated is None:
            raise ValueError("User not found after update")
        return updated

    def add_note(self, note: NewNote) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notes(
                    note_date, user_id, source, raw_text, transcript_text, project_id, manager_name,
                    lead_name, epic, status_text, done_text, plan_text, risk_text, jira_links_json, needs_review
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note.note_date,
                    note.user_id,
                    note.source,
                    note.raw_text,
                    note.transcript_text,
                    note.project_id,
                    note.manager_name,
                    note.lead_name,
                    note.epic,
                    note.status_text,
                    note.done_text,
                    note.plan_text,
                    note.risk_text,
                    json.dumps(note.jira_links, ensure_ascii=False),
                    int(note.needs_review),
                ),
            )
            return int(cursor.lastrowid)

    def get_note(self, note_id: int) -> Note | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, note_date, user_id, source, raw_text, project_id, manager_name, lead_name, epic,
                       status_text, done_text, plan_text, risk_text, jira_links_json, needs_review
                FROM notes
                WHERE id = ?
                """,
                (note_id,),
            ).fetchone()
        return self._note_from_row(row) if row else None

    def list_notes_for_date(self, target_date: date) -> list[Note]:
        note_date = target_date.isoformat()
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, note_date, user_id, source, raw_text, project_id, manager_name, lead_name, epic,
                       status_text, done_text, plan_text, risk_text, jira_links_json, needs_review
                FROM notes
                WHERE note_date = ?
                ORDER BY id ASC
                """,
                (note_date,),
            ).fetchall()
        return [self._note_from_row(row) for row in rows]

    def list_notes_for_user_on_date(self, user_id: int, target_date: date) -> list[Note]:
        note_date = target_date.isoformat()
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, note_date, user_id, source, raw_text, project_id, manager_name, lead_name, epic,
                       status_text, done_text, plan_text, risk_text, jira_links_json, needs_review
                FROM notes
                WHERE note_date = ? AND user_id = ?
                ORDER BY id ASC
                """,
                (note_date, user_id),
            ).fetchall()
        return [self._note_from_row(row) for row in rows]

    def list_unresolved_notes_for_user(
        self,
        user_id: int,
        target_date: date | None = None,
        limit: int = 50,
    ) -> list[Note]:
        with self.db.connect() as conn:
            if target_date is None:
                rows = conn.execute(
                    """
                    SELECT id, note_date, user_id, source, raw_text, project_id, manager_name, lead_name, epic,
                           status_text, done_text, plan_text, risk_text, jira_links_json, needs_review
                    FROM notes
                    WHERE user_id = ? AND needs_review = 1
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, note_date, user_id, source, raw_text, project_id, manager_name, lead_name, epic,
                           status_text, done_text, plan_text, risk_text, jira_links_json, needs_review
                    FROM notes
                    WHERE user_id = ? AND note_date = ? AND needs_review = 1
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (user_id, target_date.isoformat(), limit),
                ).fetchall()
        return [self._note_from_row(row) for row in rows]

    def get_latest_note_for_user(self, user_id: int) -> Note | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, note_date, user_id, source, raw_text, project_id, manager_name, lead_name, epic,
                       status_text, done_text, plan_text, risk_text, jira_links_json, needs_review
                FROM notes
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return self._note_from_row(row) if row else None

    def add_task(self, task: NewPMTask) -> int:
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO pm_tasks(
                    owner_user_id, title, project_id, epic, jira_key, jira_url, status,
                    priority, due_date, source
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.owner_user_id,
                    task.title.strip(),
                    task.project_id,
                    task.epic.strip(),
                    task.jira_key.strip(),
                    task.jira_url.strip(),
                    task.status.strip() or "open",
                    task.priority.strip() or "normal",
                    task.due_date.strip(),
                    task.source.strip() or "manual",
                ),
            )
            return int(cursor.lastrowid)

    def get_task(self, task_id: int) -> PMTask | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, owner_user_id, title, project_id, epic, jira_key, jira_url, status,
                       priority, due_date, source, created_at, updated_at
                FROM pm_tasks
                WHERE id = ?
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        return self._task_from_row(row) if row else None

    def list_tasks_for_user(
        self,
        user_id: int,
        statuses: list[str] | None = None,
        limit: int = 100,
    ) -> list[PMTask]:
        with self.db.connect() as conn:
            if statuses:
                cleaned = [status.strip().lower() for status in statuses if status.strip()]
                if not cleaned:
                    cleaned = ["open", "in_progress", "waiting"]
                placeholders = ", ".join("?" for _ in cleaned)
                rows = conn.execute(
                    f"""
                    SELECT id, owner_user_id, title, project_id, epic, jira_key, jira_url, status,
                           priority, due_date, source, created_at, updated_at
                    FROM pm_tasks
                    WHERE owner_user_id = ? AND status IN ({placeholders})
                    ORDER BY CASE status
                        WHEN 'in_progress' THEN 0
                        WHEN 'open' THEN 1
                        WHEN 'waiting' THEN 2
                        WHEN 'done' THEN 3
                        ELSE 4
                    END, id DESC
                    LIMIT ?
                    """,
                    [user_id, *cleaned, limit],
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, owner_user_id, title, project_id, epic, jira_key, jira_url, status,
                           priority, due_date, source, created_at, updated_at
                    FROM pm_tasks
                    WHERE owner_user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def update_task_status(self, task_id: int, owner_user_id: int, status: str) -> bool:
        next_status = status.strip().lower()
        if next_status not in {"open", "in_progress", "waiting", "done"}:
            return False
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE pm_tasks
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND owner_user_id = ?
                """,
                (next_status, task_id, owner_user_id),
            )
        return cursor.rowcount > 0

    def update_note_project(self, note_id: int, project: Project, manager_name: str, lead_name: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE notes
                SET project_id = ?, manager_name = ?, lead_name = ?, needs_review = 0
                WHERE id = ?
                """,
                (project.id, manager_name.strip(), lead_name.strip(), note_id),
            )

    def update_note_people(self, note_id: int, manager_name: str, lead_name: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE notes
                SET manager_name = ?, lead_name = ?
                WHERE id = ?
                """,
                (manager_name.strip(), lead_name.strip(), note_id),
            )

    def update_note_epic(self, note_id: int, epic_name: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE notes
                SET epic = ?
                WHERE id = ?
                """,
                (epic_name.strip(), note_id),
            )

    def update_note_analysis(
        self,
        note_id: int,
        project_id: int | None,
        manager_name: str,
        lead_name: str,
        epic: str,
        status_text: str,
        done_text: str,
        plan_text: str,
        risk_text: str,
        jira_links: list[str],
        needs_review: bool,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE notes
                SET project_id = ?,
                    manager_name = ?,
                    lead_name = ?,
                    epic = ?,
                    status_text = ?,
                    done_text = ?,
                    plan_text = ?,
                    risk_text = ?,
                    jira_links_json = ?,
                    needs_review = ?
                WHERE id = ?
                """,
                (
                    project_id,
                    manager_name.strip(),
                    lead_name.strip(),
                    epic.strip(),
                    status_text.strip(),
                    done_text.strip(),
                    plan_text.strip(),
                    risk_text.strip(),
                    json.dumps(jira_links, ensure_ascii=False),
                    int(needs_review),
                    note_id,
                ),
            )

    def save_draft(self, target_date: date, content: str, owner_user_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO drafts(draft_date, owner_user_id, content)
                VALUES(?, ?, ?)
                """,
                (target_date.isoformat(), owner_user_id, content),
            )

    def save_final_report(
        self,
        target_date: date,
        content: str,
        source_draft_id: int | None = None,
        author_user_id: int = 0,
        language: str = "ru",
        style: str = "standard",
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO final_reports(
                    report_date, content, source_draft_id, author_user_id, language, style
                )
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    target_date.isoformat(),
                    content,
                    source_draft_id,
                    author_user_id,
                    language.strip() or "ru",
                    style.strip() or "standard",
                ),
            )

    def get_latest_final_report_for_date(self, target_date: date, author_user_id: int | None = None) -> str | None:
        with self.db.connect() as conn:
            if author_user_id is None:
                row = conn.execute(
                    """
                    SELECT content
                    FROM final_reports
                    WHERE report_date = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (target_date.isoformat(),),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT content
                    FROM final_reports
                    WHERE report_date = ? AND author_user_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (target_date.isoformat(), author_user_id),
                ).fetchone()
        return row["content"] if row else None

    def get_latest_draft_for_date(self, target_date: date, owner_user_id: int | None = None) -> str | None:
        with self.db.connect() as conn:
            if owner_user_id is None:
                row = conn.execute(
                    """
                    SELECT content
                    FROM drafts
                    WHERE draft_date = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (target_date.isoformat(),),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT content
                    FROM drafts
                    WHERE draft_date = ? AND owner_user_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (target_date.isoformat(), owner_user_id),
                ).fetchone()
        return row["content"] if row else None

    def replace_jira_issues(self, issues: list[JiraIssue]) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM jira_issues")
            conn.executemany(
                """
                INSERT INTO jira_issues(
                    issue_key, summary, status, priority, assignee, reporter, watcher_names,
                    updated_at_text, project_name, project_key, issue_type, epic_name,
                    labels_text, issue_url, raw_payload_json
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        issue.issue_key,
                        issue.summary,
                        issue.status,
                        issue.priority,
                        issue.assignee,
                        issue.reporter,
                        issue.watcher_names,
                        issue.updated_at_text,
                        issue.project_name,
                        issue.project_key,
                        issue.issue_type,
                        issue.epic_name,
                        issue.labels_text,
                        issue.issue_url,
                        json.dumps(issue.__dict__, ensure_ascii=False),
                    )
                    for issue in issues
                ],
            )

    def list_jira_issues(self, limit: int | None = 100) -> list[JiraIssue]:
        with self.db.connect() as conn:
            if limit is None:
                rows = conn.execute(
                    """
                    SELECT issue_key, summary, status, priority, assignee, reporter, watcher_names,
                           updated_at_text, project_name, project_key, issue_type, epic_name,
                           labels_text, issue_url
                    FROM jira_issues
                    ORDER BY updated_at_text DESC, issue_key ASC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT issue_key, summary, status, priority, assignee, reporter, watcher_names,
                           updated_at_text, project_name, project_key, issue_type, epic_name,
                           labels_text, issue_url
                    FROM jira_issues
                    ORDER BY updated_at_text DESC, issue_key ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [self._jira_issue_from_row(row) for row in rows]

    def count_jira_issues(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM jira_issues").fetchone()
        return int(row["cnt"]) if row else 0

    def sync_epics_from_jira(self) -> int:
        issues = self.list_jira_issues(limit=None)
        updated_count = 0
        for issue in issues:
            epic_name = issue.epic_name.strip()
            if not epic_name:
                continue
            project = self._match_project_for_issue(issue)
            if project is None:
                project_name = issue.project_name.strip()
                if not project_name:
                    continue
                aliases: list[str] = [project_name]
                if issue.project_key.strip():
                    aliases.append(issue.project_key.strip())
                project = self.upsert_project(
                    name=project_name,
                    manager_name="",
                    lead_name="",
                    jira_base_url="",
                    aliases=aliases,
                    is_special_control=False,
                )
            else:
                project_key = issue.project_key.strip()
                if project_key:
                    alias_set = {alias.strip().lower() for alias in project.aliases if alias.strip()}
                    if project_key.lower() not in alias_set:
                        self.upsert_project(
                            name=project.name,
                            manager_name=project.manager_name,
                            lead_name=project.lead_name,
                            jira_base_url=project.jira_base_url,
                            aliases=project.aliases + [project_key],
                            is_special_control=project.is_special_control,
                        )
            epic = self.upsert_epic(
                project_id=project.id,
                name=epic_name,
                aliases=[epic_name],
                source="jira",
            )
            if epic is not None:
                updated_count += 1
        return updated_count

    def set_state(self, key: str, value: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_state(key, value)
                VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, value),
            )

    def delete_state(self, key: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM app_state WHERE key = ?", (key,))

    def get_state(self, key: str) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _project_from_row(self, row) -> Project:
        return Project(
            id=row["id"],
            owner_user_id=row["owner_user_id"] or 0,
            name=row["name"],
            manager_name=row["manager_name"] or "",
            lead_name=row["lead_name"] or "",
            jira_base_url=row["jira_base_url"] or "",
            aliases=json.loads(row["aliases_json"] or "[]"),
            is_special_control=bool(row["is_special_control"]),
        )

    def _user_from_row(self, row) -> UserProfile:
        return UserProfile(
            telegram_user_id=row["telegram_user_id"],
            telegram_username=row["telegram_username"] or "",
            telegram_full_name=row["telegram_full_name"] or "",
            display_name=row["display_name"] or "",
            default_manager_name=row["default_manager_name"] or "",
            default_lead_name=row["default_lead_name"] or "",
        )

    def _note_from_row(self, row) -> Note:
        return Note(
            id=row["id"],
            note_date=row["note_date"],
            user_id=row["user_id"] or 0,
            source=row["source"],
            raw_text=row["raw_text"],
            project_id=row["project_id"],
            manager_name=row["manager_name"] or "",
            lead_name=row["lead_name"] or "",
            epic=row["epic"] or "",
            status_text=row["status_text"] or "",
            done_text=row["done_text"] or "",
            plan_text=row["plan_text"] or "",
            risk_text=row["risk_text"] or "",
            jira_links=json.loads(row["jira_links_json"] or "[]"),
            needs_review=bool(row["needs_review"]),
        )

    def _jira_issue_from_row(self, row) -> JiraIssue:
        return JiraIssue(
            issue_key=row["issue_key"] or "",
            summary=row["summary"] or "",
            status=row["status"] or "",
            priority=row["priority"] or "",
            assignee=row["assignee"] or "",
            reporter=row["reporter"] or "",
            watcher_names=row["watcher_names"] or "",
            updated_at_text=row["updated_at_text"] or "",
            project_name=row["project_name"] or "",
            project_key=row["project_key"] or "",
            issue_type=row["issue_type"] or "",
            epic_name=row["epic_name"] or "",
            labels_text=row["labels_text"] or "",
            issue_url=row["issue_url"] or "",
        )

    def _epic_from_row(self, row) -> Epic:
        return Epic(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"] or "",
            aliases=json.loads(row["aliases_json"] or "[]"),
            source=row["source"] or "",
            is_active=bool(row["is_active"]),
        )

    def _template_from_row(self, row) -> ReportTemplate:
        return ReportTemplate(
            template_key=row["template_key"] or "",
            title=row["title"] or "",
            description=row["description"] or "",
            style=row["style"] or "standard",
            is_default=bool(row["is_default"]),
            is_active=bool(row["is_active"]),
        )

    def _task_from_row(self, row) -> PMTask:
        return PMTask(
            id=row["id"],
            owner_user_id=row["owner_user_id"] or 0,
            title=row["title"] or "",
            project_id=row["project_id"],
            epic=row["epic"] or "",
            jira_key=row["jira_key"] or "",
            jira_url=row["jira_url"] or "",
            status=row["status"] or "open",
            priority=row["priority"] or "normal",
            due_date=row["due_date"] or "",
            source=row["source"] or "manual",
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    def _match_project_for_issue(self, issue: JiraIssue, owner_user_id: int | None = None) -> Project | None:
        projects = self.list_projects(owner_user_id=owner_user_id)
        issue_project_key = issue.project_key.strip().lower()
        issue_project_name = issue.project_name.strip().lower()
        for project in projects:
            aliases = {alias.strip().lower() for alias in project.aliases if alias.strip()}
            if issue_project_key and issue_project_key in aliases:
                return project
            if issue_project_name and project.name.strip().lower() == issue_project_name:
                return project
            if issue_project_name and issue_project_name in project.name.strip().lower():
                return project
        return None
