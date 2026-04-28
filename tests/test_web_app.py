from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from delivery_reports.config import Settings
from delivery_reports.db import Database
from delivery_reports.repository import Repository
from delivery_reports.web_app import build_web_app


class WebAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmp_dir.name) / "web.db"
        self.settings = Settings(
            telegram_bot_token="test-bot-token",
            owner_user_id=42,
            timezone="Asia/Bishkek",
            db_path=db_path,
            default_manager_name="Анатолий Графкин",
            default_lead_name="Дмитрий Кононенко",
            daily_draft_hour=17,
            daily_draft_minute=30,
            transcribe_mode="disabled",
            whisper_model="base",
            web_host="127.0.0.1",
            web_port=8787,
            public_web_app_url="https://mini.example.com",
            web_session_secret="test-session-secret",
            super_admin_usernames=frozenset({"test_admin"}),
        )
        self.repository = Repository(Database(db_path))
        self.repository.ensure_default_report_templates()
        self.repository.upsert_project(
            name="DC701",
            manager_name="Анатолий Графкин",
            lead_name="Дмитрий Кононенко",
            jira_base_url="https://jira.example.com",
            aliases=["dc701", "цод"],
            is_special_control=False,
            owner_user_id=42,
        )
        self.client = TestClient(build_web_app(self.settings, self.repository), base_url="https://testserver")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_dashboard_requires_telegram_auth_initially(self) -> None:
        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Личный PM-кабинет", response.text)
        self.assertIn("Ожидание Telegram-сессии", response.text)

    def test_auth_route_sets_personal_session(self) -> None:
        response = self._authenticate(self.client, user_id=42, username="grafkin", full_name="Анатолий Графкин")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)

        dashboard = self.client.get("/dashboard")
        self.assertIn("СИСТЕМНЫЙ СТАТУС", dashboard.text)
        self.assertIn("DIGEST", dashboard.text)

    def test_can_add_note_and_build_team_style_draft(self) -> None:
        self._authenticate(self.client, user_id=42, username="grafkin", full_name="Анатолий Графкин")

        add_response = self.client.post(
            "/notes",
            data={
                "text": (
                    "Проект: DC701\n"
                    "Статус: тестирование\n"
                    "Что сделано:\n"
                    "- передали заявку на назначение тест-инженера\n"
                    "План на завтра:\n"
                    "- завершить кейс по L3\n"
                    "Риск: нет"
                )
            },
            follow_redirects=True,
        )

        self.assertEqual(add_response.status_code, 200)
        self.assertIn("Заметка сохранена", add_response.text)

        template_response = self.client.post(
            "/template",
            data={"template_key": "team"},
            follow_redirects=True,
        )
        self.assertEqual(template_response.status_code, 200)
        self.assertIn("Выбран шаблон", template_response.text)

        draft_response = self.client.post("/draft/build", follow_redirects=True)
        self.assertEqual(draft_response.status_code, 200)
        self.assertIn("Черновик собран", draft_response.text)

        target_date = datetime.now(ZoneInfo(self.settings.timezone)).date()
        draft = self.repository.get_latest_draft_for_date(target_date, owner_user_id=42)
        self.assertIsNotNone(draft)
        assert draft is not None
        self.assertIn("<b>Дата:</b>", draft)
        self.assertIn("<b>1. DC701</b>", draft)
        self.assertIn("<b>Статус:</b> тестирование", draft)
        self.assertNotIn("<b>Общие апдейты</b>", draft)

    def test_structured_form_creates_new_project_automatically(self) -> None:
        self._authenticate(self.client, user_id=42, username="grafkin", full_name="Анатолий Графкин")

        response = self.client.post(
            "/notes",
            data={
                "project_name": "Тест",
                "epic_name": "Pilot",
                "status_text": "Тесты",
                "done_text": "Тестовая версия mini app MVP",
                "plan_text": "Планирую проверку отправки в тг",
                "risk_text": "риск того что не отправить сообщение в Тг",
                "links_text": "OM-33824\nhttps://jira.example.com/browse/OM-33824",
                "action": "save",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Заметка сохранена", response.text)
        project = self.repository.find_project_by_name_or_alias("Тест", owner_user_id=42)
        self.assertIsNotNone(project)
        target_date = datetime.now(ZoneInfo(self.settings.timezone)).date()
        notes = self.repository.list_notes_for_user_on_date(42, target_date)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].epic, "Pilot")
        self.assertEqual(notes[0].jira_links, ["https://jira.example.com/browse/OM-33824"])
        unresolved = self.repository.list_unresolved_notes_for_user(
            42,
            target_date=target_date,
        )
        self.assertEqual(len(unresolved), 0)

    def test_can_add_and_update_task(self) -> None:
        self._authenticate(self.client, user_id=42, username="grafkin", full_name="Анатолий Графкин")

        add_response = self.client.post(
            "/tasks",
            data={"title": "Согласовать ночное окно по DC701"},
            follow_redirects=True,
        )
        self.assertEqual(add_response.status_code, 200)
        self.assertIn("Задача #", add_response.text)

        tasks = self.repository.list_tasks_for_user(42, statuses=["open"])
        self.assertEqual(len(tasks), 1)

        update_response = self.client.post(
            f"/tasks/{tasks[0].id}/status",
            data={"status": "done"},
            follow_redirects=True,
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertIn("Статус задачи", update_response.text)
        done_tasks = self.repository.list_tasks_for_user(42, statuses=["done"])
        self.assertEqual(len(done_tasks), 1)

    def test_can_send_draft_to_telegram(self) -> None:
        self._authenticate(self.client, user_id=42, username="grafkin", full_name="Анатолий Графкин")

        self.client.post(
            "/notes",
            data={
                "project_name": "DC701",
                "status_text": "в работе",
                "done_text": "переносим серверы",
                "plan_text": "согласовать ночные окна",
                "risk_text": "нет",
                "action": "save_build",
            },
            follow_redirects=True,
        )

        with patch("delivery_reports.web_app._send_report_to_telegram", new=AsyncMock()) as send_mock:
            response = self.client.post("/draft/send", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Черновик отправлен в Telegram", response.text)
        send_mock.assert_awaited()

    def test_dashboard_v2_renders_intent_badges_for_today_notes(self) -> None:
        v2_client = self._build_v2_client()
        self._authenticate(v2_client, user_id=42, username="grafkin", full_name="Анатолий Графкин")

        # 1) Done-only note.
        v2_client.post(
            "/notes",
            data={
                "project_name": "DC701",
                "done_text": "закрыли релиз 2.4",
                "action": "save",
            },
            follow_redirects=True,
        )
        # 2) Plan-only note.
        v2_client.post(
            "/notes",
            data={
                "project_name": "DC701",
                "plan_text": "завтра демо с заказчиком",
                "action": "save",
            },
            follow_redirects=True,
        )

        dashboard = v2_client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("intent-done", dashboard.text)
        self.assertIn("intent-plan", dashboard.text)
        self.assertIn("✓ Сделано", dashboard.text)
        self.assertIn("→ План", dashboard.text)

    def test_dashboard_v2_marks_inbox_card_with_intent_and_no_project_chip(self) -> None:
        v2_client = self._build_v2_client()
        self._authenticate(v2_client, user_id=42, username="grafkin", full_name="Анатолий Графкин")

        v2_client.post(
            "/notes",
            data={"text": "обсуждали релиз без явного проекта", "action": "save"},
            follow_redirects=True,
        )

        dashboard = v2_client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("v2-intent-badge", dashboard.text)
        self.assertIn("v2-note-item-project--none", dashboard.text)

    def _build_v2_client(self) -> TestClient:
        v2_settings = dataclasses.replace(self.settings, dashboard_ui_version="v2")
        return TestClient(build_web_app(v2_settings, self.repository), base_url="https://testserver")


    def test_second_user_does_not_see_first_user_data(self) -> None:
        self._authenticate(self.client, user_id=42, username="grafkin", full_name="Анатолий Графкин")
        self.client.post(
            "/notes",
            data={
                "project_name": "DC701",
                "status_text": "в работе",
                "done_text": "секретный апдейт по первому пользователю",
                "plan_text": "закончить проверку",
                "risk_text": "нет",
                "action": "save",
            },
            follow_redirects=True,
        )

        second_client = TestClient(build_web_app(self.settings, self.repository), base_url="https://testserver")
        self._authenticate(second_client, user_id=77, username="demo77", full_name="Второй Пользователь")
        response = second_client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("секретный апдейт по первому пользователю", response.text)
        self.assertIsNone(self.repository.find_project_by_name_or_alias("DC701", owner_user_id=77))

    def _authenticate(self, client: TestClient, user_id: int, username: str, full_name: str):
        return client.post(
            "/auth/telegram",
            json={"init_data": self._build_init_data(user_id, username, full_name)},
        )

    def _build_init_data(self, user_id: int, username: str, full_name: str) -> str:
        first_name, *tail = full_name.split(" ")
        last_name = " ".join(tail)
        user_payload = {
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "language_code": "ru",
        }
        base_pairs = {
            "auth_date": str(int(time.time())),
            "user": json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
        }
        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(base_pairs.items()))
        secret_key = hmac.new(b"WebAppData", self.settings.telegram_bot_token.encode("utf-8"), hashlib.sha256).digest()
        signature = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        return urlencode({**base_pairs, "hash": signature})


if __name__ == "__main__":
    unittest.main()
