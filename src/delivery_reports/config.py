from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


def _read_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _read_optional_int(name: str) -> int | None:
    value = os.getenv(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = ""
    owner_user_id: int | None = None
    timezone: str = "Asia/Bishkek"
    db_path: Path = Path("data/delivery_reports.db")
    default_manager_name: str = ""
    default_lead_name: str = ""
    daily_draft_hour: int = 17
    daily_draft_minute: int = 30
    transcribe_mode: str = "local_whisper"
    whisper_model: str = "base"
    web_host: str = "127.0.0.1"
    web_port: int = 8787
    public_web_app_url: str = ""
    web_session_secret: str = ""
    super_admin_usernames: frozenset[str] = frozenset({"pm_vibe"})  # e.g. {'PM_vibe'}


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        owner_user_id=_read_optional_int("OWNER_USER_ID"),
        timezone=os.getenv("TIMEZONE", "Asia/Bishkek").strip() or "Asia/Bishkek",
        db_path=Path(os.getenv("DB_PATH", "data/delivery_reports.db")),
        default_manager_name=os.getenv("DEFAULT_MANAGER_NAME", "").strip(),
        default_lead_name=os.getenv("DEFAULT_LEAD_NAME", "").strip(),
        daily_draft_hour=_read_int("DAILY_DRAFT_HOUR", 17),
        daily_draft_minute=_read_int("DAILY_DRAFT_MINUTE", 30),
        transcribe_mode=os.getenv("TRANSCRIBE_MODE", "local_whisper").strip() or "local_whisper",
        whisper_model=os.getenv("WHISPER_MODEL", "base").strip() or "base",
        web_host=os.getenv("WEB_HOST", "127.0.0.1").strip() or "127.0.0.1",
        web_port=_read_int("WEB_PORT", 8787),
        public_web_app_url=os.getenv("PUBLIC_WEB_APP_URL", "").strip(),
        web_session_secret=os.getenv("WEB_SESSION_SECRET", "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        super_admin_usernames=frozenset(
            u.strip().lstrip("@").lower()
            for u in os.getenv("SUPER_ADMIN_USERNAMES", "PM_vibe").split(",")
            if u.strip()
        ),
    )
