"""
Tests for the Clean Architecture API layer:
- src/api/dependencies.py
- src/api/main.py
- src/api/routes.py
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
import os
os.environ.setdefault("AMO_SUBDOMAIN", "tokutools")
os.environ.setdefault("AMO_ACCESS_TOKEN", "test_token")


# ═══════════════════════════════════════════════════════════════════
# TESTS: src/api/dependencies.py
# ═══════════════════════════════════════════════════════════════════

class TestDependencies:
    """Tests for dependency injection functions."""

    @patch.dict("os.environ", {"AMO_SUBDOMAIN": "testdomain", "AMO_ACCESS_TOKEN": "tok123"})
    def test_get_amo_client_returns_client(self):
        from src.api.dependencies import get_amo_client
        client = get_amo_client()
        assert client.subdomain == "testdomain"
        assert client.access_token == "tok123"

    @patch.dict("os.environ", {"AMO_SUBDOMAIN": "", "AMO_ACCESS_TOKEN": ""})
    def test_get_amo_client_empty_env(self):
        from src.api.dependencies import get_amo_client
        client = get_amo_client()
        assert client.subdomain == ""
        assert client.access_token == ""

    @patch.dict("os.environ", {"YADISK_TOKEN": "yadisk_test_token"})
    def test_get_yadisk_client_returns_client(self):
        from src.api.dependencies import get_yadisk_client
        client = get_yadisk_client()
        assert client.token == "yadisk_test_token"

    @patch.dict("os.environ", {"YADISK_TOKEN": ""})
    def test_get_yadisk_client_empty_env(self):
        from src.api.dependencies import get_yadisk_client
        client = get_yadisk_client()
        assert client.token == ""


# ═══════════════════════════════════════════════════════════════════
# TESTS: src/api/routes.py
# ═══════════════════════════════════════════════════════════════════

class TestRoutes:
    """Tests for FastAPI routes (Clean Architecture API)."""

    def setup_method(self):
        """Create a test client with mocked dependencies."""
        from src.api.routes import router
        from src.api.dependencies import get_amo_client, get_yadisk_client
        from fastapi import FastAPI
        self.app = FastAPI()
        self.app.include_router(router)
        # Override dependencies to avoid real API calls
        self.mock_amo = MagicMock()
        self.mock_yadisk = MagicMock()
        self.app.dependency_overrides[get_amo_client] = lambda: self.mock_amo
        self.app.dependency_overrides[get_yadisk_client] = lambda: self.mock_yadisk
        self.client = TestClient(self.app)

    def teardown_method(self):
        self.app.dependency_overrides.clear()

    def test_health_check(self):
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "RETEK" in data["service"]

    def test_webhook_leads_add(self):
        response = self.client.post(
            "/webhook",
            data={"leads[add][0][id]": "12345"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["event"] == "leads[add]"

    def test_webhook_unhandled_event(self):
        response = self.client.post(
            "/webhook",
            data={"some[unknown][event]": "value"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"

    def test_webhook_note_add_bot_own_note_ignored(self):
        # The route parses idx from notes[add][X][id] key
        # idx is extracted as: key.split("][")[2].replace("]", "") = "0"
        # Then it looks for notes[add][0][element_id] and notes[add][0][text]
        response = self.client.post(
            "/webhook",
            data={
                "notes[add][0][id]": "999",
                "notes[add][0][element_id]": "123",
                "notes[add][0][text]": "🤖 Принял ссылку",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "bot_own_note"

    def test_webhook_note_add_with_yadisk_link(self):
        # Note: Action3Service.process_note runs in background_tasks,
        # so the route returns immediately with accepted status
        with patch("src.api.routes.Action3Service") as mock_action3_cls:
            mock_service = MagicMock()
            mock_action3_cls.return_value = mock_service
            response = self.client.post(
                "/webhook",
                data={
                    "notes[add][0][id]": "999",
                    "notes[add][0][element_id]": "456",
                    "notes[add][0][text]": "Вот ссылка https://disk.yandex.ru/d/abc123",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "accepted"
            assert data["action"] == "action3"
            assert data["event"] == "notes[add]"

    def test_webhook_note_add_no_trigger(self):
        response = self.client.post(
            "/webhook",
            data={
                "notes[add][0][id]": "999",
                "notes[add][0][element_id]": "456",
                "notes[add][0][text]": "Просто комментарий без ссылки",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"


# ═══════════════════════════════════════════════════════════════════
# TESTS: src/api/main.py
# ═══════════════════════════════════════════════════════════════════

class TestApiMain:
    """Tests for the FastAPI application setup in src/api/main.py."""

    @patch("src.api.main.scheduler")
    def test_app_exists_and_has_routes(self, mock_scheduler):
        from src.api.main import app
        assert app is not None
        assert app.title == "RETEK amoCRM Microservice"

    @patch("src.api.main.scheduler")
    def test_startup_event(self, mock_scheduler):
        from src.api.main import startup_event
        startup_event()
        mock_scheduler.add_job.assert_called()
        mock_scheduler.start.assert_called_once()

    @patch("src.api.main.scheduler")
    def test_shutdown_event(self, mock_scheduler):
        from src.api.main import shutdown_event
        shutdown_event()
        mock_scheduler.shutdown.assert_called_once()

    @patch("src.api.main.get_amo_client")
    @patch("src.api.main.CronService")
    def test_run_hourly_cron_success(self, mock_cron_cls, mock_get_client):
        from src.api.main import run_hourly_cron
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_service = MagicMock()
        mock_cron_cls.return_value = mock_service

        run_hourly_cron()

        mock_get_client.assert_called_once()
        mock_cron_cls.assert_called_once_with(mock_client)
        mock_service.check_deadlines_and_escalate.assert_called_once()

    @patch("src.api.main.get_amo_client")
    def test_run_hourly_cron_exception_handled(self, mock_get_client):
        from src.api.main import run_hourly_cron
        mock_get_client.side_effect = Exception("Connection error")
        # Should not raise
        run_hourly_cron()
