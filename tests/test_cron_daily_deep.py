"""
Глубокие тесты для src/microservice/cron_daily.py.
Покрывает: _archive_leads, _process_lead_for_archive, _validate_archive_fields,
_handle_incomplete_lead, _create_return_task, _check_return_dates, _check_lead_return_date.
"""
import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def mock_amo_client():
    with patch("src.microservice.cron_daily.AmoClient") as MockCls:
        mock_instance = MagicMock()
        MockCls.return_value = mock_instance
        MockCls.get_custom_field_value = MagicMock(return_value=None)
        yield MockCls, mock_instance


class TestArchiveLeads:
    """Tests for _archive_leads."""

    def test_no_archive_status_configured(self, mock_amo_client):
        """If TO_ARCHIVE status is not configured, returns early."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver

        with patch("src.microservice.cron_daily.ActiveStatuses") as MockStatuses:
            MockStatuses.TO_ARCHIVE = None
            archiver = DailyArchiver(dry_run=False)
            archiver.client = mock_instance
            archiver._archive_leads()
        mock_instance.get_all_leads_in_status.assert_not_called()

    def test_no_leads_to_archive(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance
        mock_instance.get_all_leads_in_status.return_value = []

        archiver._archive_leads()
        assert archiver.stats["found_to_archive"] == 0

    def test_leads_found_and_processed(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance
        mock_instance.get_all_leads_in_status.return_value = [
            {"id": 1, "name": "Lead 1"},
            {"id": 2, "name": "Lead 2"},
        ]

        with patch.object(archiver, "_process_lead_for_archive") as mock_process:
            archiver._archive_leads()
        assert archiver.stats["found_to_archive"] == 2
        assert mock_process.call_count == 2


class TestProcessLeadForArchive:
    """Tests for _process_lead_for_archive."""

    def test_missing_fields_creates_task(self, mock_amo_client):
        """Lead with missing required fields gets a task."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance

        lead = {"id": 1, "name": "Test", "responsible_user_id": 100}
        with patch.object(archiver, "_validate_archive_fields", return_value=["Причина закрытия"]):
            archiver._process_lead_for_archive(lead)
        assert archiver.stats["incomplete_fields"] == 1
        mock_instance.create_task.assert_called_once()

    def test_no_archive_destination(self, mock_amo_client):
        """Lead with all fields but no archive destination."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance
        lead = {"id": 1, "name": "Test", "responsible_user_id": 100}
        with patch.object(archiver, "_validate_archive_fields", return_value=[]):
            with patch.object(MockCls, "get_custom_field_value", return_value=None):
                with patch.object(archiver, "_handle_incomplete_lead") as mock_handle:
                    archiver._process_lead_for_archive(lead)
        # Should call _handle_incomplete_lead with missing archive destination
        mock_handle.assert_called_once_with(lead, ["Архивное назначение итоговое"])

    def test_unknown_archive_destination(self, mock_amo_client):
        """Lead with unknown archive destination."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance

        lead = {"id": 1, "name": "Test", "responsible_user_id": 100}
        with patch.object(archiver, "_validate_archive_fields", return_value=[]):
            with patch.object(MockCls, "get_custom_field_value", return_value="Неизвестное направление"):
                with patch("src.microservice.cron_daily.resolve_archive_destination", return_value=(None, None)):
                    archiver._process_lead_for_archive(lead)
        assert archiver.stats["errors"] == 1

    def test_successful_archive(self, mock_amo_client):
        """Lead is successfully archived."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance
        mock_instance.move_lead.return_value = True

        lead = {"id": 1, "name": "Test", "responsible_user_id": 100}
        with patch.object(archiver, "_validate_archive_fields", return_value=[]):
            with patch.object(MockCls, "get_custom_field_value", side_effect=["Спецоснастка", None, "Не наш ассортимент", None]):
                with patch("src.microservice.cron_daily.resolve_archive_destination", return_value=(2, 200001)):
                    archiver._process_lead_for_archive(lead)
        assert archiver.stats["archived_ok"] == 1
        mock_instance.move_lead.assert_called_once_with(1, 2, 200001)
        mock_instance.add_note.assert_called_once()

    def test_archive_move_fails(self, mock_amo_client):
        """Lead move fails — error counted."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance
        mock_instance.move_lead.return_value = False

        lead = {"id": 1, "name": "Test", "responsible_user_id": 100}
        with patch.object(archiver, "_validate_archive_fields", return_value=[]):
            with patch.object(MockCls, "get_custom_field_value", side_effect=["Спецоснастка", None, None]):
                with patch("src.microservice.cron_daily.resolve_archive_destination", return_value=(2, 200001)):
                    archiver._process_lead_for_archive(lead)
        assert archiver.stats["errors"] == 1
        assert archiver.stats["archived_ok"] == 0

    def test_archive_with_return_date(self, mock_amo_client):
        """Successful archive with return date creates return task."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance
        mock_instance.move_lead.return_value = True
        mock_instance.create_task_at_date.return_value = {"id": 1}

        lead = {"id": 1, "name": "Test", "responsible_user_id": 100}
        future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        with patch.object(archiver, "_validate_archive_fields", return_value=[]):
            with patch.object(MockCls, "get_custom_field_value", side_effect=["Спецоснастка", "Причина", future]):
                with patch("src.microservice.cron_daily.resolve_archive_destination", return_value=(2, 200001)):
                    archiver._process_lead_for_archive(lead)
        assert archiver.stats["archived_ok"] == 1
        assert archiver.stats["return_tasks_created"] == 1


class TestValidateArchiveFields:
    """Tests for _validate_archive_fields."""

    def test_all_fields_present(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance

        lead = {"id": 1}
        with patch.object(MockCls, "get_custom_field_value", return_value="filled"):
            missing = archiver._validate_archive_fields(lead)
        assert missing == []

    def test_some_fields_missing(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance

        lead = {"id": 1}
        # Return None for some fields
        with patch.object(MockCls, "get_custom_field_value", side_effect=[None, "filled", None, "filled"]):
            with patch("src.microservice.cron_daily.ARCHIVE_REQUIRED_FIELDS", [1001, 1002, 1003, 1004]):
                with patch("src.microservice.cron_daily.ARCHIVE_REQUIRED_FIELD_NAMES", {1001: "Причина", 1002: "Направление", 1003: "Дата", 1004: "Тип"}):
                    missing = archiver._validate_archive_fields(lead)
        assert len(missing) == 2
        assert "Причина" in missing
        assert "Дата" in missing


class TestCreateReturnTask:
    """Tests for _create_return_task."""

    def test_valid_date_string(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance
        mock_instance.create_task_at_date.return_value = {"id": 1}

        lead = {"id": 5, "name": "Test", "responsible_user_id": 100}
        archiver._create_return_task(lead, "2025-06-15")
        mock_instance.create_task_at_date.assert_called_once()
        assert archiver.stats["return_tasks_created"] == 1

    def test_unix_timestamp_date(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance
        mock_instance.create_task_at_date.return_value = {"id": 1}

        lead = {"id": 5, "name": "Test", "responsible_user_id": 100}
        ts = str(int((datetime.now() + timedelta(days=30)).timestamp()))
        archiver._create_return_task(lead, ts)
        mock_instance.create_task_at_date.assert_called_once()
        assert archiver.stats["return_tasks_created"] == 1

    def test_invalid_date_format(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance

        lead = {"id": 5, "name": "Test", "responsible_user_id": 100}
        archiver._create_return_task(lead, "invalid-date")
        mock_instance.create_task_at_date.assert_not_called()

    def test_dot_format_date(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance
        mock_instance.create_task_at_date.return_value = {"id": 1}

        lead = {"id": 5, "name": "Test", "responsible_user_id": 100}
        archiver._create_return_task(lead, "15.06.2025")
        mock_instance.create_task_at_date.assert_called_once()


class TestCheckReturnDates:
    """Tests for _check_return_dates and _check_lead_return_date."""

    def test_iterates_archive_pipelines(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance
        mock_instance.get_leads.return_value = []

        archiver._check_return_dates()
        # Should call get_leads for each archive pipeline
        assert mock_instance.get_leads.call_count >= 2

    def test_check_lead_no_return_date(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance

        lead = {"id": 1}
        with patch.object(MockCls, "get_custom_field_value", return_value=None):
            archiver._check_lead_return_date(lead)
        mock_instance.create_task.assert_not_called()

    def test_check_lead_return_date_in_future(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance

        lead = {"id": 1}
        future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        with patch.object(MockCls, "get_custom_field_value", return_value=future):
            archiver._check_lead_return_date(lead)
        mock_instance.create_task.assert_not_called()

    def test_check_lead_return_date_today(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance

        lead = {"id": 1, "name": "Test", "responsible_user_id": 100}
        today = datetime.now().strftime("%Y-%m-%d")
        with patch.object(MockCls, "get_custom_field_value", return_value=today):
            archiver._check_lead_return_date(lead)
        mock_instance.create_task.assert_called_once()
        assert archiver.stats["return_tasks_created"] == 1

    def test_check_lead_return_date_past(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance

        lead = {"id": 1, "name": "Test", "responsible_user_id": 100}
        past = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        with patch.object(MockCls, "get_custom_field_value", return_value=past):
            archiver._check_lead_return_date(lead)
        mock_instance.create_task.assert_called_once()

    def test_check_lead_return_date_unix_timestamp(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_daily import DailyArchiver
        archiver = DailyArchiver(dry_run=False)
        archiver.client = mock_instance

        lead = {"id": 1, "name": "Test", "responsible_user_id": 100}
        # Unix timestamp in the past
        past_ts = str(int((datetime.now() - timedelta(days=2)).timestamp()))
        with patch.object(MockCls, "get_custom_field_value", return_value=past_ts):
            archiver._check_lead_return_date(lead)
        mock_instance.create_task.assert_called_once()


class TestRunDaily:
    """Tests for run_daily entry point."""

    def test_run_daily_returns_stats(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        mock_instance.get_all_leads_in_status.return_value = []
        mock_instance.get_leads.return_value = []

        from src.microservice.cron_daily import run_daily
        stats = run_daily(dry_run=True)
        assert "found_to_archive" in stats
        assert "errors" in stats

    def test_run_daily_handles_exception(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        mock_instance.get_all_leads_in_status.side_effect = Exception("API Error")

        from src.microservice.cron_daily import run_daily
        stats = run_daily(dry_run=True)
        assert stats["errors"] >= 1
