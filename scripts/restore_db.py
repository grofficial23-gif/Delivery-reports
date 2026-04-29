"""Restore SQLite DB from ``delivery_reports_latest.db`` in the backup folder.

Uses ``delivery_reports.config.load_settings`` for ``DB_PATH``.
Creates parent directories for the DB path if needed.

Optional: ``DELIVERY_REPORTS_BACKUP_DIR`` — same as ``backup_db.py``.

Usage::

    python scripts/restore_db.py

Exit code ``1`` if the latest backup file is missing; ``0`` on success.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from delivery_reports.config import load_settings  # noqa: E402


def _backups_dir() -> Path:
    import os

    raw = os.environ.get("DELIVERY_REPORTS_BACKUP_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (_REPO_ROOT / "backups").resolve()


def _resolve_db_path(settings_db: Path) -> Path:
    p = Path(settings_db)
    return p.resolve() if p.is_absolute() else (_REPO_ROOT / p).resolve()


def main() -> int:
    settings = load_settings()
    dest = _resolve_db_path(settings.db_path)
    src = _backups_dir() / "delivery_reports_latest.db"

    if not src.is_file():
        print(f"Nothing to restore: missing backup {src}", file=sys.stderr)
        return 1

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    print(f"Restored {src} -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
