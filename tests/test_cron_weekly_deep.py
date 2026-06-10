"""
Deeper tests for cron_weekly.py:
- WeeklyControl._create_stuck_report_task
- WeeklyControl._check_wip_limits
- run_weekly
"""
import pytest
from unittest.mock import patch, MagicMock
import os


@pytest.fixture
def mock_env():
    """Mock environment variables."""
    env = {
        "AMO_DOMAIN": "test.amocrm.ru",
        "AMO_ACCESS_TOKEN": "test_token",
        "DRY_RUN": "1",
        "PIPELINE_ACTIVE": "100",
        "USER_MANAGER": "9001",
        "USER_EMPLOYEE_2_SALES": "5001",
        "USER_EMPLOYEE_3_BUYER": "5002",
        "WIP_LIMIT_EMPLOYEE_2": "15",
        "WIP_LIMIT_EMPLOYEE_3": "10",
        "STUCK_LEAD_DAYS": "7",
    }
    with patch.dict("os.environ", env):
        yield


class TestCreateStuckReportTask:
    """Tests for WeeklyControl._create_stuck_report_task."""

    @patch("src.microservice.cron_weekly.AmoClient")
    def test_creates_task_for_stuck_leads(self, mock_amo_cls, mock_env):
        """Creates a task for the manager with stuck leads info."""
        from src.microservice.cron_weekly import WeeklyControl

        mock_client = MagicMock()
        mock_client.create_task.return_value = {"id": 999}
        mock_amo_cls.return_value = mock_client

        wc = WeeklyControl(dry_run=False)
        wc.client = mock_client

        stuck_batch = [
            {"lead": {"id": 100, "name": "Lead A", "responsible_user_id": 5001}, "days_stuck": 10},
            {"lead": {"id": 101, "name": "Lead B", "responsible_user_id": 5002}, "days_stuck": 8},
        ]

        wc._create_stuck_report_task(stuck_batch)
        mock_client.create_task.assert_called_once()
        call_kwargs = mock_client.create_task.call_args
        # Verify task text contains stuck leads info
        assert "ЗАВИСШИЕ КАРТОЧКИ" in str(call_kwargs)
        assert wc.stats["tasks_created"] == 1

    @patch("src.microservice.cron_weekly.Users")
    @patch("src.microservice.cron_weekly.AmoClient")
    def test_no_manager_configured_skips(self, mock_amo_cls, mock_users, mock_env):
        """If MANAGER is not configured, skip task creation."""
        from src.microservice.cron_weekly import WeeklyControl

        mock_users.MANAGER = None
        mock_client = MagicMock()
        mock_amo_cls.return_value = mock_client

        wc = WeeklyControl(dry_run=False)
        wc.client = mock_client

        stuck_batch = [
            {"lead": {"id": 100, "name": "Lead A", "responsible_user_id": 5001}, "days_stuck": 10},
        ]

        wc._create_stuck_report_task(stuck_batch)
        mock_client.create_task.assert_not_called()

    @patch("src.microservice.cron_weekly.AmoClient")
    def test_task_creation_failure_no_increment(self, mock_amo_cls, mock_env):
        """If task creation returns None, stats not incremented."""
        from src.microservice.cron_weekly import WeeklyControl

        mock_client = MagicMock()
        mock_client.create_task.return_value = None  # Failed
        mock_amo_cls.return_value = mock_client

        wc = WeeklyControl(dry_run=False)
        wc.client = mock_client

        stuck_batch = [
            {"lead": {"id": 100, "name": "Lead A", "responsible_user_id": 5001}, "days_stuck": 10},
        ]

        wc._create_stuck_report_task(stuck_batch)
        assert wc.stats["tasks_created"] == 0

    @patch("src.microservice.cron_weekly.AmoClient")
    def test_task_text_contains_lead_names(self, mock_amo_cls, mock_env):
        """Task text contains lead names and days stuck."""
        from src.microservice.cron_weekly import WeeklyControl

        mock_client = MagicMock()
        mock_client.create_task.return_value = {"id": 1}
        mock_amo_cls.return_value = mock_client

        wc = WeeklyControl(dry_run=False)
        wc.client = mock_client

        stuck_batch = [
            {"lead": {"id": 100, "name": "Тендер Газпром", "responsible_user_id": 5001}, "days_stuck": 14},
        ]

        wc._create_stuck_report_task(stuck_batch)
        call_kwargs = mock_client.create_task.call_args
        text_arg = str(call_kwargs)
        assert "Тендер Газпром" in text_arg
        assert "14" in text_arg


class TestCheckWipLimits:
    """Tests for WeeklyControl._check_wip_limits."""

    @patch("src.microservice.cron_weekly.Users")
    @patch("src.microservice.cron_weekly.AmoClient")
    def test_wip_exceeded_increments_violations(self, mock_amo_cls, mock_users, mock_env):
        """When WIP limit exceeded, violations counter increments."""
        from src.microservice.cron_weekly import WeeklyControl

        # Set Users to have real IDs so the check doesn't skip
        mock_users.EMPLOYEE_2_SALES = 5001
        mock_users.EMPLOYEE_3_BUYER = 5002

        mock_client = MagicMock()
        # Return 25 leads assigned to user 5001 (limit is 20)
        leads = [{"id": i, "responsible_user_id": 5001, "status_id": 200} for i in range(25)]
        mock_client.get_leads.return_value = leads
        mock_amo_cls.return_value = mock_client

        wc = WeeklyControl(dry_run=False)
        wc.client = mock_client

        wc._check_wip_limits()
        assert wc.stats["wip_violations"] >= 1

    @patch("src.microservice.cron_weekly.AmoClient")
    def test_wip_within_limits_no_violations(self, mock_amo_cls, mock_env):
        """When WIP within limits, no violations."""
        from src.microservice.cron_weekly import WeeklyControl

        mock_client = MagicMock()
        # Return only 5 leads (limit is 15)
        leads = [{"id": i, "responsible_user_id": 5001, "status_id": 200} for i in range(5)]
        mock_client.get_leads.return_value = leads
        mock_amo_cls.return_value = mock_client

        wc = WeeklyControl(dry_run=False)
        wc.client = mock_client

        wc._check_wip_limits()
        assert wc.stats["wip_violations"] == 0

    @patch("src.microservice.cron_weekly.ActiveStatuses")
    @patch("src.microservice.cron_weekly.AmoClient")
    def test_archive_status_leads_not_counted(self, mock_amo_cls, mock_active_statuses, mock_env):
        """Leads in TO_ARCHIVE status are not counted toward WIP."""
        from src.microservice.cron_weekly import WeeklyControl

        mock_active_statuses.TO_ARCHIVE = 999
        mock_client = MagicMock()
        # All leads have TO_ARCHIVE status
        leads = [{"id": i, "responsible_user_id": 5001, "status_id": 999} for i in range(20)]
        mock_client.get_leads.return_value = leads
        mock_amo_cls.return_value = mock_client

        wc = WeeklyControl(dry_run=False)
        wc.client = mock_client

        wc._check_wip_limits()
        assert wc.stats["wip_violations"] == 0

    @patch("src.microservice.cron_weekly.AmoClient")
    def test_no_leads_no_violations(self, mock_amo_cls, mock_env):
        """No leads means no violations."""
        from src.microservice.cron_weekly import WeeklyControl

        mock_client = MagicMock()
        mock_client.get_leads.return_value = []
        mock_amo_cls.return_value = mock_client

        wc = WeeklyControl(dry_run=False)
        wc.client = mock_client

        wc._check_wip_limits()
        assert wc.stats["wip_violations"] == 0


class TestRunWeekly:
    """Tests for run_weekly function."""

    @patch("src.microservice.cron_weekly.AmoClient")
    def test_run_weekly_returns_stats(self, mock_amo_cls, mock_env):
        """run_weekly returns stats dict."""
        from src.microservice.cron_weekly import run_weekly

        mock_client = MagicMock()
        mock_client.get_leads.return_value = []
        mock_amo_cls.return_value = mock_client

        result = run_weekly(dry_run=True)
        assert isinstance(result, dict)
        assert "total_checked" in result
        assert "stuck_found" in result
        assert "wip_violations" in result
        assert "tasks_created" in result

    @patch("src.microservice.cron_weekly.AmoClient")
    def test_run_weekly_handles_exception(self, mock_amo_cls, mock_env):
        """run_weekly handles exceptions gracefully."""
        from src.microservice.cron_weekly import run_weekly

        mock_client = MagicMock()
        mock_client.get_leads.side_effect = Exception("API Error")
        mock_amo_cls.return_value = mock_client

        # Should not raise
        result = run_weekly(dry_run=True)
        assert isinstance(result, dict)
