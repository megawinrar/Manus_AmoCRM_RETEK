"""
Глубокие тесты для src/microservice/main.py.
Покрывает: FastAPI app, lifespan, scheduler setup, all endpoints (root, status,
run/hourly, run/daily, run/weekly, run/monthly, run/yadisk).
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

os.environ.setdefault("AMO_DOMAIN", "tokutools.amocrm.ru")
os.environ.setdefault("AMO_ACCESS_TOKEN", "test_access_token")
os.environ.setdefault("AMO_REFRESH_TOKEN", "test_refresh_token")
os.environ.setdefault("AMO_CLIENT_ID", "test_client_id")
os.environ.setdefault("AMO_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("AMO_TOKEN_EXPIRES_AT", "9999999999")
os.environ.setdefault("YANDEX_GPT_API_KEY", "test_key")
os.environ.setdefault("YANDEX_GPT_FOLDER_ID", "test_folder")
os.environ.setdefault("YADISK_TOKEN", "test_yadisk_token")
os.environ.setdefault("STATUS_1_LLM", "100001")
os.environ.setdefault("STATUS_2_CHECK", "100002")
os.environ.setdefault("STATUS_3_SOZ_CALL", "100003")
os.environ.setdefault("STATUS_4_SOZ_WAIT", "100004")
os.environ.setdefault("STATUS_5_PURCHASING", "100005")
os.environ.setdefault("STATUS_6_KP_PREP", "100006")
os.environ.setdefault("STATUS_7_KP_DEALER", "100007")
os.environ.setdefault("STATUS_8_DEALER_DEC", "100008")
os.environ.setdefault("STATUS_9_BIDDING", "100009")
os.environ.setdefault("STATUS_10_PRODUCTION", "100010")
os.environ.setdefault("STATUS_11_ARCHIVE", "100011")
os.environ.setdefault("ARCH_DIR_SPEC", "200001")
os.environ.setdefault("ARCH_DIR_HSS", "200002")
os.environ.setdefault("ARCH_DIR_CARBIDE", "200003")
os.environ.setdefault("ARCH_DIR_DIAMOND", "200004")
os.environ.setdefault("ARCH_DIR_OUT", "200005")
os.environ.setdefault("ARCH_DIR_DUPL", "200006")
os.environ.setdefault("ARCH_DIR_CHECK", "200007")
os.environ.setdefault("ARCH_SOZ_WAIT", "300001")
os.environ.setdefault("ARCH_SOZ_CALL", "300002")
os.environ.setdefault("ARCH_SOZ_30D", "300003")
os.environ.setdefault("AMO_PIPELINE_ACTIVE_ID", "1")
os.environ.setdefault("AMO_PIPELINE_ARCHIVE_DIRECTIONS_ID", "2")
os.environ.setdefault("AMO_PIPELINE_ARCHIVE_SOZ_ID", "3")
os.environ.setdefault("DRY_RUN", "1")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked scheduler."""
    with patch("src.microservice.main.scheduler") as mock_scheduler:
        mock_scheduler.get_jobs.return_value = []
        mock_scheduler.running = True
        from src.microservice.main import app
        with TestClient(app) as c:
            yield c


class TestRootEndpoint:
    """Tests for GET /."""

    def test_root_returns_service_info(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "RETEK amoCRM Microservice"
        assert "version" in data
        assert "endpoints" in data
        assert data["mode"] == "dry-run"

    def test_root_has_all_endpoints(self, client):
        resp = client.get("/")
        data = resp.json()
        endpoints = data["endpoints"]
        assert "webhook" in endpoints
        assert "health" in endpoints
        assert "status" in endpoints
        assert "run_hourly" in endpoints
        assert "run_daily" in endpoints


class TestStatusEndpoint:
    """Tests for GET /status."""

    def test_status_returns_scheduler_info(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "scheduler_running" in data
        assert "jobs" in data
        assert "timestamp" in data

    def test_status_shows_dry_run_mode(self, client):
        resp = client.get("/status")
        data = resp.json()
        assert data["mode"] == "dry-run"


class TestRunHourlyEndpoint:
    """Tests for POST /run/hourly."""

    @patch("src.microservice.main.run_hourly")
    def test_run_hourly_success(self, mock_run, client):
        mock_run.return_value = {"checked": 10, "escalated": 2, "errors": 0}
        resp = client.post("/run/hourly")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["stats"]["checked"] == 10

    @patch("src.microservice.main.run_hourly")
    def test_run_hourly_empty(self, mock_run, client):
        mock_run.return_value = {"checked": 0, "escalated": 0, "errors": 0}
        resp = client.post("/run/hourly")
        assert resp.status_code == 200


class TestRunDailyEndpoint:
    """Tests for POST /run/daily."""

    @patch("src.microservice.main.run_daily")
    def test_run_daily_success(self, mock_run, client):
        mock_run.return_value = {"found_to_archive": 5, "archived_ok": 3, "errors": 0}
        resp = client.post("/run/daily")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["stats"]["found_to_archive"] == 5

    @patch("src.microservice.main.run_daily")
    def test_run_daily_with_errors(self, mock_run, client):
        mock_run.return_value = {"found_to_archive": 2, "archived_ok": 0, "errors": 2}
        resp = client.post("/run/daily")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"]["errors"] == 2


class TestRunWeeklyEndpoint:
    """Tests for POST /run/weekly."""

    @patch("src.microservice.main.run_weekly")
    def test_run_weekly_success(self, mock_run, client):
        mock_run.return_value = {"stuck_found": 3, "tasks_created": 2}
        resp = client.post("/run/weekly")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"


class TestRunMonthlyEndpoint:
    """Tests for POST /run/monthly."""

    @patch("src.microservice.main.run_monthly")
    def test_run_monthly_success(self, mock_run, client):
        mock_run.return_value = {"date": "2025-06-01", "total_archive": 50}
        resp = client.post("/run/monthly")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["report_date"] == "2025-06-01"


class TestRunYadiskEndpoint:
    """Tests for POST /run/yadisk."""

    @patch("src.microservice.main.run_yadisk_scan")
    def test_run_yadisk_success(self, mock_run, client):
        mock_run.return_value = {"files_found": 10, "leads_created": 3}
        resp = client.post("/run/yadisk")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["stats"]["files_found"] == 10


class TestSetupScheduler:
    """Tests for setup_scheduler function."""

    def test_setup_scheduler_adds_jobs(self):
        with patch("src.microservice.main.scheduler") as mock_scheduler:
            from src.microservice.main import setup_scheduler
            setup_scheduler()
            # Should add at least 5 jobs (hourly, daily, weekly, yadisk, monthly)
            assert mock_scheduler.add_job.call_count >= 5

    def test_setup_scheduler_job_ids(self):
        with patch("src.microservice.main.scheduler") as mock_scheduler:
            from src.microservice.main import setup_scheduler
            setup_scheduler()
            job_ids = [call.kwargs.get("id") or call[1].get("id", "") for call in mock_scheduler.add_job.call_args_list]
            # Check some expected job IDs
            all_args = str(mock_scheduler.add_job.call_args_list)
            assert "hourly" in all_args
            assert "daily" in all_args


class TestJobWrappers:
    """Tests for _job_hourly, _job_daily, etc."""

    @patch("src.microservice.main.run_hourly")
    def test_job_hourly_wrapper(self, mock_run):
        mock_run.return_value = {"checked": 0}
        from src.microservice.main import _job_hourly
        _job_hourly()
        mock_run.assert_called_once()

    @patch("src.microservice.main.run_daily")
    def test_job_daily_wrapper(self, mock_run):
        mock_run.return_value = {"found_to_archive": 0}
        from src.microservice.main import _job_daily
        _job_daily()
        mock_run.assert_called_once()

    @patch("src.microservice.main.run_weekly")
    def test_job_weekly_wrapper(self, mock_run):
        mock_run.return_value = {}
        from src.microservice.main import _job_weekly
        _job_weekly()
        mock_run.assert_called_once()

    @patch("src.microservice.main.run_yadisk_scan")
    def test_job_yadisk_wrapper(self, mock_run):
        mock_run.return_value = {}
        from src.microservice.main import _job_yadisk_scan
        _job_yadisk_scan()
        mock_run.assert_called_once()

    @patch("src.microservice.main.run_monthly")
    def test_job_monthly_wrapper(self, mock_run):
        mock_run.return_value = {}
        from src.microservice.main import _job_monthly
        _job_monthly()
        mock_run.assert_called_once()
