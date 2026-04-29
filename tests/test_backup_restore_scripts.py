"""Tests for scripts/backup_db.py and scripts/restore_db.py."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


class BackupRestoreScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backup_db = _REPO_ROOT / "scripts" / "backup_db.py"
        self.restore_db = _REPO_ROOT / "scripts" / "restore_db.py"

    def test_backup_creates_latest_copy(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_dir = tmp_path / "data"
            data_dir.mkdir()
            db_file = data_dir / "delivery_reports.db"
            payload = b"sqlite-test-\x00-step34"
            db_file.write_bytes(payload)

            backup_root = tmp_path / "backups"
            env = {
                **os.environ,
                "DB_PATH": str(db_file.resolve()),
                "DELIVERY_REPORTS_BACKUP_DIR": str(backup_root),
                "TELEGRAM_BOT_TOKEN": "",
            }
            r = subprocess.run(
                [sys.executable, str(self.backup_db)],
                cwd=str(_REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            latest = backup_root / "delivery_reports_latest.db"
            self.assertTrue(latest.is_file())
            self.assertEqual(latest.read_bytes(), payload)
            stamped = list(backup_root.glob("delivery_reports_*.db"))
            self.assertEqual(len(stamped), 2, "expected timestamped + latest")  # latest + one stamped
            self.assertIn("latest", r.stdout.lower() or r.stderr.lower())

    def test_restore_copies_latest_to_db_path(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            backup_root = tmp_path / "backups"
            backup_root.mkdir()
            payload = b"restored-content"
            (backup_root / "delivery_reports_latest.db").write_bytes(payload)

            dest = tmp_path / "nested" / "data" / "delivery_reports.db"
            env = {
                **os.environ,
                "DB_PATH": str(dest.resolve()),
                "DELIVERY_REPORTS_BACKUP_DIR": str(backup_root),
                "TELEGRAM_BOT_TOKEN": "",
            }
            self.assertFalse(dest.exists())
            r = subprocess.run(
                [sys.executable, str(self.restore_db)],
                cwd=str(_REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.read_bytes(), payload)

    def test_restore_missing_backup_exits_nonzero(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            backup_root = tmp_path / "empty_backups"
            backup_root.mkdir()
            dest = tmp_path / "data" / "delivery_reports.db"
            env = {
                **os.environ,
                "DB_PATH": str(dest.resolve()),
                "DELIVERY_REPORTS_BACKUP_DIR": str(backup_root),
                "TELEGRAM_BOT_TOKEN": "",
            }
            r = subprocess.run(
                [sys.executable, str(self.restore_db)],
                cwd=str(_REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
