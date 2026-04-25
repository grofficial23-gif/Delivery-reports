from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from delivery_reports.db import Database
from delivery_reports.services.subscription import (
    Plan,
    SubscriptionService,
)


class SubscriptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp_dir.name) / "sub.db"
        self.db = Database(db_path)
        self.service = SubscriptionService(self.db)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_new_user_has_free_plan(self) -> None:
        self.assertEqual(self.service.get_user_plan(42), Plan.FREE)

    def test_free_plan_blocks_voice_notes(self) -> None:
        self.assertFalse(self.service.check_feature(42, "voice_notes"))

    def test_free_plan_limits_projects(self) -> None:
        self.assertEqual(self.service.check_limit(42, "max_projects"), 3)

    def test_activate_pro_subscription(self) -> None:
        sub_id = self.service.activate_subscription(
            user_id=42,
            plan=Plan.PRO,
            payment_method="telegram_stars",
            payment_ref="star_123",
        )
        self.assertGreater(sub_id, 0)
        self.assertEqual(self.service.get_user_plan(42), Plan.PRO)

    def test_pro_plan_allows_voice_notes(self) -> None:
        self.service.activate_subscription(user_id=42, plan=Plan.PRO)
        self.assertTrue(self.service.check_feature(42, "voice_notes"))

    def test_pro_plan_unlimited_projects(self) -> None:
        self.service.activate_subscription(user_id=42, plan=Plan.PRO)
        self.assertIsNone(self.service.check_limit(42, "max_projects"))

    def test_cancel_subscription_reverts_to_free(self) -> None:
        self.service.activate_subscription(user_id=42, plan=Plan.PRO)
        self.assertEqual(self.service.get_user_plan(42), Plan.PRO)
        self.service.cancel_subscription(42)
        self.assertEqual(self.service.get_user_plan(42), Plan.FREE)

    def test_new_subscription_replaces_old(self) -> None:
        self.service.activate_subscription(user_id=42, plan=Plan.PRO)
        self.service.activate_subscription(user_id=42, plan=Plan.TEAM)
        self.assertEqual(self.service.get_user_plan(42), Plan.TEAM)

    def test_subscription_isolation_between_users(self) -> None:
        self.service.activate_subscription(user_id=42, plan=Plan.PRO)
        self.assertEqual(self.service.get_user_plan(42), Plan.PRO)
        self.assertEqual(self.service.get_user_plan(77), Plan.FREE)

    def test_plan_display_name(self) -> None:
        self.assertEqual(self.service.plan_display_name(Plan.FREE), "Бесплатный")
        self.assertEqual(self.service.plan_display_name(Plan.PRO), "PRO")
        self.assertEqual(self.service.plan_display_name(Plan.TEAM), "Команда")


if __name__ == "__main__":
    unittest.main()
