"""
Тесты для cron-модулей:
- src/microservice/cron_hourly.py (HourlyControl, run_hourly)
- src/microservice/cron_daily.py (DailyArchiver, run_daily)
- src/microservice/cron_weekly.py (WeeklyControl, run_weekly)
- src/microservice/cron_backup.py (run_backup, save_backup_local, fetch_all_leads)

Запуск:
    pytest tests/test_cron_jobs.py -v
"""

import os
import sys
import json
import time
import tempfile
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
os.environ.setdefault("ARCH_SOZ_90D", "300004")
os.environ.setdefault("ARCH_SOZ_FACTORY", "300005")
os.environ.setdefault("ARCH_SOZ_IRRELEVANT", "300006")
os.environ.setdefault("USER_EMPLOYEE_2", "9000001")
os.environ.setdefault("USER_EMPLOYEE_3", "9000002")
os.environ.setdefault("USER_MANAGER", "9000003")
os.environ.setdefault("BACKUP_DIR", "/tmp/test_backups")
os.environ.setdefault("AMO_PIPELINE_ACTIVE_ID", "10984442")
os.environ.setdefault("AMO_PIPELINE_ARCHIVE_DIRECTIONS_ID", "10984454")
os.environ.setdefault("AMO_PIPELINE_ARCHIVE_SOZ_ID", "10984466")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.microservice.cron_hourly import HourlyControl, run_hourly
from src.microservice.cron_daily import DailyArchiver, run_daily
from src.microservice.cron_weekly import WeeklyControl, run_weekly
from src.microservice.cron_backup import (
    save_backup_local,
    fetch_all_leads,
    fetch_tasks,
    run_backup,
)


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_lead_p1():
    """Лид P1 без активной задачи."""
    return {
        "id": 1001,
        "name": "[P1] СРОЧНО — НПО Высокоточные — 15.07",
        "status_id": 100005,
        "pipeline_id": 10984442,
        "responsible_user_id": 9000002,
        "updated_at": int(time.time()) - 7200,
        "custom_fields_values": [
            {"field_id": 380309, "values": [{"value": "Р1", "enum_id": 215673}]},
            {"field_id": 380317, "values": [{"value": "2025-07-15"}]},
        ],
    }


@pytest.fixture
def sample_lead_stuck():
    """Зависший лид (>7 дней без движения)."""
    return {
        "id": 2001,
        "name": "[P3] — Старый тендер",
        "status_id": 100003,
        "pipeline_id": 10984442,
        "responsible_user_id": 9000001,
        "updated_at": int(time.time()) - (10 * 86400),
        "custom_fields_values": [],
    }


@pytest.fixture
def sample_lead_to_archive():
    """Лид в статусе 'К архивированию'."""
    return {
        "id": 3001,
        "name": "[P2] — Архивный тендер",
        "status_id": 100011,
        "pipeline_id": 10984442,
        "responsible_user_id": 9000001,
        "updated_at": int(time.time()) - 3600,
        "custom_fields_values": [
            {"field_id": 380305, "values": [{"value": "Запрос котировок / реальные торги"}]},
            {"field_id": 380309, "values": [{"value": "Р2", "enum_id": 215675}]},
            {"field_id": 380311, "values": [{"value": "Твердосплав"}]},
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ HourlyControl
# ═══════════════════════════════════════════════════════════════════

class TestHourlyControl:
    """Тесты ежечасного контроля."""

    @patch("src.microservice.cron_hourly.AmoClient")
    def test_run_no_leads(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = []
        mock_client.get_overdue_tasks.return_value = []
        mock_cls.return_value = mock_client

        hc = HourlyControl(dry_run=True)
        result = hc.run()
        assert isinstance(result, dict)

    @patch("src.microservice.cron_hourly.AmoClient")
    def test_run_with_leads(self, mock_cls, sample_lead_p1):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = [sample_lead_p1]
        mock_client.get_tasks_for_lead.return_value = []
        mock_client.get_overdue_tasks.return_value = []
        mock_client.update_lead.return_value = True
        mock_client.create_task.return_value = True
        mock_client.add_note.return_value = True
        mock_cls.return_value = mock_client

        hc = HourlyControl(dry_run=False)
        result = hc.run()
        assert isinstance(result, dict)

    @patch("src.microservice.cron_hourly.AmoClient")
    def test_dry_run_no_writes(self, mock_cls, sample_lead_p1):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = [sample_lead_p1]
        mock_client.get_tasks_for_lead.return_value = []
        mock_client.get_overdue_tasks.return_value = []
        mock_cls.return_value = mock_client

        hc = HourlyControl(dry_run=True)
        hc.run()
        mock_client.update_lead.assert_not_called()
        mock_client.create_task.assert_not_called()

    @patch("src.microservice.cron_hourly.AmoClient")
    def test_escalate_by_deadline(self, mock_cls):
        deadline_soon = (datetime.now() + timedelta(hours=20)).strftime("%Y-%m-%d")
        lead = {
            "id": 5001,
            "name": "[P3] — Тест эскалации",
            "status_id": 100005,
            "pipeline_id": 10984442,
            "responsible_user_id": 9000002,
            "updated_at": int(time.time()) - 1800,
            "custom_fields_values": [
                {"field_id": 380309, "values": [{"value": "Р3", "enum_id": 215677}]},
                {"field_id": 380317, "values": [{"value": deadline_soon}]},
            ],
        }
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = [lead]
        mock_client.get_tasks_for_lead.return_value = []
        mock_client.get_overdue_tasks.return_value = []
        mock_client.update_lead.return_value = True
        mock_client.create_task.return_value = True
        mock_client.add_note.return_value = True
        mock_cls.return_value = mock_client

        hc = HourlyControl(dry_run=False)
        result = hc.run()
        assert isinstance(result, dict)

    @patch("src.microservice.cron_hourly.AmoClient")
    def test_control_overdue_tasks(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = []
        mock_client.get_overdue_tasks.return_value = [
            {"id": 501, "entity_id": 1001, "text": "Задача", "responsible_user_id": 9000001}
        ]
        mock_client.create_task.return_value = True
        mock_cls.return_value = mock_client

        hc = HourlyControl(dry_run=True)
        hc.run()


class TestRunHourly:
    @patch("src.microservice.cron_hourly.AmoClient")
    def test_run_hourly_function(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = []
        mock_client.get_overdue_tasks.return_value = []
        mock_cls.return_value = mock_client

        result = run_hourly(dry_run=True)
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ DailyArchiver
# ═══════════════════════════════════════════════════════════════════

class TestDailyArchiver:
    """Тесты ежедневного архивирования."""

    @patch("src.microservice.cron_daily.AmoClient")
    def test_run_no_leads(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = []
        mock_cls.return_value = mock_client

        da = DailyArchiver(dry_run=True)
        result = da.run()
        assert isinstance(result, dict)

    @patch("src.microservice.cron_daily.AmoClient")
    def test_run_with_archive_lead(self, mock_cls, sample_lead_to_archive):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = [sample_lead_to_archive]
        mock_client.update_lead.return_value = True
        mock_client.move_lead.return_value = True
        mock_client.add_note.return_value = True
        mock_cls.return_value = mock_client

        da = DailyArchiver(dry_run=False)
        result = da.run()
        assert isinstance(result, dict)

    @patch("src.microservice.cron_daily.AmoClient")
    def test_dry_run_no_writes(self, mock_cls, sample_lead_to_archive):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = [sample_lead_to_archive]
        mock_cls.return_value = mock_client

        da = DailyArchiver(dry_run=True)
        da.run()
        mock_client.move_lead.assert_not_called()
        mock_client.update_lead.assert_not_called()


class TestRunDaily:
    @patch("src.microservice.cron_daily.AmoClient")
    def test_run_daily_function(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = []
        mock_cls.return_value = mock_client

        result = run_daily(dry_run=True)
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ WeeklyControl
# ═══════════════════════════════════════════════════════════════════

class TestWeeklyControl:
    """Тесты еженедельного контроля."""

    @patch("src.microservice.cron_weekly.AmoClient")
    def test_run_no_leads(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = []
        mock_client.get_leads.return_value = []
        mock_cls.return_value = mock_client

        wc = WeeklyControl(dry_run=True)
        result = wc.run()
        assert isinstance(result, dict)

    @patch("src.microservice.cron_weekly.AmoClient")
    def test_find_stuck_leads(self, mock_cls, sample_lead_stuck):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = [sample_lead_stuck]
        mock_client.get_leads.return_value = []
        mock_client.create_task.return_value = True
        mock_client.add_note.return_value = True
        mock_cls.return_value = mock_client

        wc = WeeklyControl(dry_run=True)
        result = wc.run()
        assert isinstance(result, dict)

    @patch("src.microservice.cron_weekly.AmoClient")
    def test_check_wip_limits(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = list(range(50))  # 50 items
        mock_client.get_leads.return_value = []
        mock_cls.return_value = mock_client

        wc = WeeklyControl(dry_run=True)
        result = wc.run()
        assert isinstance(result, dict)


class TestRunWeekly:
    @patch("src.microservice.cron_weekly.AmoClient")
    def test_run_weekly_function(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_all_leads_in_status.return_value = []
        mock_client.get_leads.return_value = []
        mock_cls.return_value = mock_client

        result = run_weekly(dry_run=True)
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ cron_backup
# ═══════════════════════════════════════════════════════════════════

class TestCronBackup:
    """Тесты модуля бэкапа."""

    @patch("src.microservice.cron_backup.requests.get")
    def test_fetch_all_leads(self, mock_get):
        # First call returns 2 leads, second returns 204 (end)
        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {
            "_embedded": {"leads": [{"id": 1}, {"id": 2}]}
        }
        resp_empty = MagicMock()
        resp_empty.status_code = 204
        mock_get.side_effect = [resp_ok, resp_empty]

        result = fetch_all_leads(with_notes=False, with_contacts=False)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_save_backup_local(self):
        leads = [{"id": 1, "name": "Lead 1"}, {"id": 2, "name": "Lead 2"}]
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("src.microservice.cron_backup.BACKUP_DIR", tmp_dir):
                path = save_backup_local(leads, tasks=[])
                assert path is not None
                assert os.path.exists(path)

    @patch("src.microservice.cron_backup.save_backup_yadisk")
    @patch("src.microservice.cron_backup.save_backup_local")
    @patch("src.microservice.cron_backup.fetch_all_leads")
    @patch("src.microservice.cron_backup.fetch_tasks")
    def test_run_backup(self, mock_tasks, mock_leads, mock_save_local, mock_save_yadisk):
        mock_leads.return_value = [{"id": 1}]
        mock_tasks.return_value = [{"id": 10}]
        mock_save_local.return_value = "/tmp/backup.json"
        mock_save_yadisk.return_value = True

        run_backup(with_notes=False, upload_yadisk=False)
        mock_leads.assert_called_once()
        mock_save_local.assert_called_once()
