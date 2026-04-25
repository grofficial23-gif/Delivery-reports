"""Super Admin service — управление пользователями, подписками и статистикой.

Доступен только пользователям из SUPER_ADMIN_USERNAMES (например @PM_vibe).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..config import Settings
from ..db import Database
from .subscription import Plan, SubscriptionService


@dataclass
class UserSummary:
    telegram_user_id: int
    telegram_username: str
    telegram_full_name: str
    display_name: str
    plan: str
    notes_count: int
    drafts_count: int
    tasks_count: int
    projects_count: int
    last_note_date: Optional[str]
    registered_at: str


@dataclass
class PlatformStats:
    total_users: int
    active_today: int
    active_this_week: int
    total_notes: int
    total_drafts: int
    total_tasks: int
    plans_breakdown: dict[str, int]  # plan -> count


class AdminService:
    """Полный контроль над платформой для super admin."""

    def __init__(self, db: Database, settings: Settings):
        self._db = db
        self._settings = settings
        self._sub = SubscriptionService(db)

    # ── Проверка прав ──────────────────────────────────────────────────

    def is_super_admin(self, username: str) -> bool:
        """Проверяет, является ли пользователь super admin."""
        if not username:
            return False
        clean = username.lstrip("@").lower()
        return clean in self._settings.super_admin_usernames

    def is_super_admin_by_id(self, user_id: int) -> bool:
        """Проверка по user_id через БД (для случаев без username)."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT telegram_username FROM users WHERE telegram_user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return False
            return self.is_super_admin(row["telegram_username"] or "")

    # ── Статистика платформы ───────────────────────────────────────────

    def get_platform_stats(self) -> PlatformStats:
        """Общая статистика по всей платформе."""
        with self._db.connect() as conn:
            total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_notes = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            total_drafts = conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
            total_tasks = conn.execute("SELECT COUNT(*) FROM pm_tasks").fetchone()[0]

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            week_ago = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            active_today = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM notes WHERE note_date = ?",
                (today,),
            ).fetchone()[0]

            active_this_week = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM notes "
                "WHERE note_date >= date('now', '-7 days')",
            ).fetchone()[0]

        # Plans breakdown
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT plan, COUNT(*) as cnt FROM subscriptions "
                "WHERE status = 'active' GROUP BY plan"
            ).fetchall()
            plans_breakdown = {Plan.FREE: total_users}  # default everyone is free
            for row in rows:
                plans_breakdown[row["plan"]] = row["cnt"]
                plans_breakdown[Plan.FREE] -= row["cnt"]
            if plans_breakdown[Plan.FREE] < 0:
                plans_breakdown[Plan.FREE] = 0

        return PlatformStats(
            total_users=total_users,
            active_today=active_today,
            active_this_week=active_this_week,
            total_notes=total_notes,
            total_drafts=total_drafts,
            total_tasks=total_tasks,
            plans_breakdown=plans_breakdown,
        )

    # ── Управление пользователями ──────────────────────────────────────

    def list_users(self, limit: int = 20, offset: int = 0) -> list[UserSummary]:
        """Список всех пользователей с их статистикой."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT telegram_user_id, telegram_username, telegram_full_name, "
                "display_name, created_at FROM users "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()

        summaries = []
        for row in rows:
            uid = row["telegram_user_id"]
            plan = self._sub.get_user_plan(uid)
            with self._db.connect() as conn:
                notes_count = conn.execute(
                    "SELECT COUNT(*) FROM notes WHERE user_id = ?", (uid,)
                ).fetchone()[0]
                drafts_count = conn.execute(
                    "SELECT COUNT(*) FROM drafts WHERE owner_user_id = ?", (uid,)
                ).fetchone()[0]
                tasks_count = conn.execute(
                    "SELECT COUNT(*) FROM pm_tasks WHERE owner_user_id = ?", (uid,)
                ).fetchone()[0]
                projects_count = conn.execute(
                    "SELECT COUNT(*) FROM projects WHERE owner_user_id = ?", (uid,)
                ).fetchone()[0]
                last_note = conn.execute(
                    "SELECT note_date FROM notes WHERE user_id = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (uid,),
                ).fetchone()

            summaries.append(UserSummary(
                telegram_user_id=uid,
                telegram_username=row["telegram_username"] or "",
                telegram_full_name=row["telegram_full_name"] or "",
                display_name=row["display_name"] or "",
                plan=plan,
                notes_count=notes_count,
                drafts_count=drafts_count,
                tasks_count=tasks_count,
                projects_count=projects_count,
                last_note_date=last_note["note_date"] if last_note else None,
                registered_at=row["created_at"],
            ))
        return summaries

    def find_user(self, query: str) -> Optional[UserSummary]:
        """Найти пользователя по username или user_id."""
        with self._db.connect() as conn:
            if query.lstrip("@").isdigit():
                row = conn.execute(
                    "SELECT * FROM users WHERE telegram_user_id = ?",
                    (int(query.lstrip("@")),),
                ).fetchone()
            else:
                clean = query.lstrip("@").lower()
                row = conn.execute(
                    "SELECT * FROM users WHERE LOWER(telegram_username) = ?",
                    (clean,),
                ).fetchone()
        if not row:
            return None
        uid = row["telegram_user_id"]
        plan = self._sub.get_user_plan(uid)
        with self._db.connect() as conn:
            notes_count = conn.execute(
                "SELECT COUNT(*) FROM notes WHERE user_id = ?", (uid,)
            ).fetchone()[0]
            last_note = conn.execute(
                "SELECT note_date FROM notes WHERE user_id = ? "
                "ORDER BY created_at DESC LIMIT 1", (uid,)
            ).fetchone()
        return UserSummary(
            telegram_user_id=uid,
            telegram_username=row["telegram_username"] or "",
            telegram_full_name=row["telegram_full_name"] or "",
            display_name=row["display_name"] or "",
            plan=plan,
            notes_count=notes_count,
            drafts_count=0,
            tasks_count=0,
            projects_count=0,
            last_note_date=last_note["note_date"] if last_note else None,
            registered_at=row["created_at"],
        )

    # ── Управление подписками ──────────────────────────────────────────

    def grant_pro(self, user_id: int, months: int = 1) -> bool:
        """Выдать PRO подписку пользователю."""
        from datetime import timedelta
        expires = (
            datetime.now(timezone.utc) + timedelta(days=30 * months)
        ).strftime("%Y-%m-%d")
        self._sub.activate_subscription(
            user_id=user_id,
            plan=Plan.PRO,
            payment_method="admin_grant",
            payment_ref=f"admin_grant_{months}mo",
            expires_at=expires,
        )
        return True

    def grant_team(self, user_id: int, months: int = 1) -> bool:
        """Выдать TEAM подписку пользователю."""
        from datetime import timedelta
        expires = (
            datetime.now(timezone.utc) + timedelta(days=30 * months)
        ).strftime("%Y-%m-%d")
        self._sub.activate_subscription(
            user_id=user_id,
            plan=Plan.TEAM,
            payment_method="admin_grant",
            payment_ref=f"admin_grant_team_{months}mo",
            expires_at=expires,
        )
        return True

    def revoke_subscription(self, user_id: int) -> bool:
        """Отозвать активную подписку."""
        return self._sub.cancel_subscription(user_id)

    # ── Форматирование для Telegram ────────────────────────────────────

    def format_stats_message(self, stats: PlatformStats) -> str:
        """Форматирует PlatformStats в HTML для Telegram."""
        plans = stats.plans_breakdown
        pro_count = plans.get(Plan.PRO, 0)
        team_count = plans.get(Plan.TEAM, 0)
        free_count = plans.get(Plan.FREE, 0)

        return (
            "📊 <b>Статистика платформы</b>\n\n"
            f"👤 <b>Пользователи:</b> {stats.total_users}\n"
            f"  · Активны сегодня: <b>{stats.active_today}</b>\n"
            f"  · Активны за неделю: <b>{stats.active_this_week}</b>\n\n"
            f"📋 <b>Планы:</b>\n"
            f"  · Free: {free_count}\n"
            f"  · PRO: <b>{pro_count}</b>\n"
            f"  · Team: <b>{team_count}</b>\n\n"
            f"📝 Заметок: {stats.total_notes}\n"
            f"📄 Черновиков: {stats.total_drafts}\n"
            f"✅ Задач: {stats.total_tasks}"
        )

    def format_user_message(self, user: UserSummary) -> str:
        """Форматирует UserSummary в HTML для Telegram."""
        plan_emoji = {"free": "🆓", "pro": "⭐", "team": "👥"}.get(user.plan, "❓")
        username_part = f"@{user.telegram_username}" if user.telegram_username else "нет username"
        return (
            f"👤 <b>{user.display_name or user.telegram_full_name}</b>\n"
            f"  {username_part} · <code>{user.telegram_user_id}</code>\n\n"
            f"  {plan_emoji} Тариф: <b>{user.plan.upper()}</b>\n"
            f"  📝 Заметок: {user.notes_count}\n"
            f"  📅 Последняя: {user.last_note_date or 'нет'}\n"
            f"  📁 Проектов: {user.projects_count}\n"
            f"  ✅ Задач: {user.tasks_count}\n"
            f"  🗓 Зарегистрирован: {user.registered_at[:10]}"
        )
