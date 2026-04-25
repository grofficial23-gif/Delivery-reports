"""Subscription management and feature gating for monetization."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..db import Database


class Plan:
    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"


PLAN_LIMITS: dict[str, dict] = {
    Plan.FREE: {
        "max_projects": 3,
        "voice_notes": False,
        "history_days": 7,
        "templates": ["standard"],
        "mini_app": True,
        "ai_edit": False,
        "weekly_summary": False,
        "jira_import": False,
        "export": False,
    },
    Plan.PRO: {
        "max_projects": None,  # unlimited
        "voice_notes": True,
        "history_days": 90,
        "templates": None,  # all
        "mini_app": True,
        "ai_edit": True,
        "weekly_summary": True,
        "jira_import": True,
        "export": True,
    },
    Plan.TEAM: {
        "max_projects": None,
        "voice_notes": True,
        "history_days": 365,
        "templates": None,
        "mini_app": True,
        "ai_edit": True,
        "weekly_summary": True,
        "jira_import": True,
        "export": True,
        "team_reports": True,
        "admin_panel": True,
    },
}


@dataclass(frozen=True)
class Subscription:
    id: int
    user_id: int
    plan: str
    status: str
    started_at: str
    expires_at: Optional[str]
    payment_method: str
    payment_ref: str


class SubscriptionService:
    """Manages subscriptions and feature access checks."""

    def __init__(self, db: Database):
        self._db = db

    def get_active_subscription(self, user_id: int) -> Optional[Subscription]:
        """Return the active subscription for a user, or None (= free plan)."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE user_id = ? AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if row is None:
                return None
            return Subscription(
                id=row["id"],
                user_id=row["user_id"],
                plan=row["plan"],
                status=row["status"],
                started_at=row["started_at"],
                expires_at=row["expires_at"],
                payment_method=row["payment_method"],
                payment_ref=row["payment_ref"],
            )

    def get_user_plan(self, user_id: int) -> str:
        """Return the user's current plan name, considering TEAM inheritance."""
        # First, check if the user is in a team
        with self._db.connect() as conn:
            team_row = conn.execute(
                """
                SELECT t.owner_user_id 
                FROM team_members tm
                JOIN teams t ON tm.team_id = t.id
                WHERE tm.user_id = ?
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            
            if team_row:
                owner_id = team_row["owner_user_id"]
                owner_sub = self.get_active_subscription(owner_id)
                if owner_sub and owner_sub.plan == Plan.TEAM:
                    return Plan.TEAM

        # If not in a team or owner doesn't have TEAM, check their personal plan
        sub = self.get_active_subscription(user_id)
        if sub and sub.plan in (Plan.PRO, Plan.TEAM):
            return sub.plan
        return Plan.FREE

    def check_feature(self, user_id: int, feature: str) -> bool:
        """Check if the user has access to a specific feature."""
        plan = self.get_user_plan(user_id)
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS[Plan.FREE])
        value = limits.get(feature)
        if value is None:
            return True  # None means unlimited / all access
        return bool(value)

    def check_limit(self, user_id: int, limit_name: str) -> int | None:
        """Return a numeric limit for the user, or None if unlimited."""
        plan = self.get_user_plan(user_id)
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS[Plan.FREE])
        return limits.get(limit_name)

    def activate_subscription(
        self,
        user_id: int,
        plan: str,
        payment_method: str = "telegram_stars",
        payment_ref: str = "",
        expires_at: Optional[str] = None,
    ) -> int:
        """Create or update a subscription for a user."""
        with self._db.connect() as conn:
            # Deactivate any existing active subscriptions
            conn.execute(
                "UPDATE subscriptions SET status = 'replaced', "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE user_id = ? AND status = 'active'",
                (user_id,),
            )
            cursor = conn.execute(
                "INSERT INTO subscriptions "
                "(user_id, plan, status, payment_method, payment_ref, expires_at) "
                "VALUES (?, ?, 'active', ?, ?, ?)",
                (user_id, plan, payment_method, payment_ref, expires_at),
            )
            return cursor.lastrowid or 0

    def cancel_subscription(self, user_id: int) -> bool:
        """Cancel the active subscription for a user."""
        with self._db.connect() as conn:
            cursor = conn.execute(
                "UPDATE subscriptions SET status = 'cancelled', "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE user_id = ? AND status = 'active'",
                (user_id,),
            )
            return (cursor.rowcount or 0) > 0

    def plan_display_name(self, plan: str) -> str:
        """Human-readable plan name."""
        names = {
            Plan.FREE: "Бесплатный",
            Plan.PRO: "PRO",
            Plan.TEAM: "Команда",
            Plan.ENTERPRISE: "Enterprise",
        }
        return names.get(plan, plan)

    def get_days_left(self, user_id: int) -> int | None:
        """Return the number of days left on the active subscription, or None if no expiry."""
        sub = self.get_active_subscription(user_id)
        if not sub or not sub.expires_at:
            return None
        try:
            expires = datetime.fromisoformat(sub.expires_at)
            # Make sure it's timezone-aware if comparing to UTC
            if expires.tzinfo is None:
                from datetime import timezone
                expires = expires.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days = (expires - now).days
            return max(0, days)
        except Exception:
            return None
