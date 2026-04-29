"""Copy the configured SQLite DB into ``backups/`` with a timestamp + ``latest``.

Uses ``delivery_reports.config.load_settings`` (``DB_PATH`` from env / ``.env``).

Optional: ``DELIVERY_REPORTS_BACKUP_DIR`` — absolute path to backup folder
(default: ``<repo>/backups``). Intended for tests / custom layouts.

Usage::

    python scripts/backup_db.py

Exit code ``0`` if a backup was written or if the source DB file is missing
(no crash; prints a short message).
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
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
    src = _resolve_db_path(settings.db_path)

    if not src.is_file():
        print(f"Skip backup: no database at {src}")
        return 0

    dest_dir = _backups_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stamped = dest_dir / f"delivery_reports_{stamp}.db"
    latest = dest_dir / "delivery_reports_latest.db"

    shutil.copy2(src, stamped)
    shutil.copy2(src, latest)

    print(f"Source:      {src}")
    print(f"Timestamped: {stamped}")
    print(f"Latest:      {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
