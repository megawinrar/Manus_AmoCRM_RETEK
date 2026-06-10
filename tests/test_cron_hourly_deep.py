"""
Глубокие тесты для src/microservice/cron_hourly.py.
Покрывает: _try_escalate_lead, _control_priority_leads, _check_priority_lead,
_create_control_task, _control_no_next_action, _control_overdue_tasks.
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
    with patch("src.microservice.cron_hourly.AmoClient") as MockCls:
        mock_instance = MagicMock()
        MockCls.return_value = mock_instance
        # Static method
        MockCls.get_custom_field_value = MagicMock(return_value=None)
        yield MockCls, mock_instance


class TestTryEscalateLead:
    """Tests for HourlyControl._try_escalate_lead."""

    def test_no_priority_returns_false(self, mock_amo_client):
        """If lead has no priority field, skip."""
        MockCls, mock_instance = mock_amo_client
        MockCls.get_custom_field_value.return_value = None

        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance

        lead = {"id": 1, "custom_fields_values": []}
        # Patch the static method to return None for priority
        with patch.object(MockCls, "get_custom_field_value", return_value=None):
            result = ctrl._try_escalate_lead(lead)
        assert result is False

    def test_no_deadline_returns_false(self, mock_amo_client):
        """If lead has priority but no deadline, skip."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance

        lead = {"id": 1}
        # First call returns priority, second returns None (no deadline)
        with patch.object(MockCls, "get_custom_field_value", side_effect=["Р3 — Средний", None]):
            result = ctrl._try_escalate_lead(lead)
        assert result is False

    def test_no_escalation_needed(self, mock_amo_client):
        """If auto_escalate returns no escalation, return False."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance

        lead = {"id": 1}
        # Far future deadline - no escalation needed
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        with patch.object(MockCls, "get_custom_field_value", side_effect=["Р3 — Средний", future_date]):
            with patch("src.microservice.cron_hourly.auto_escalate_priority", return_value=("Р3 — Средний", False, "")):
                result = ctrl._try_escalate_lead(lead)
        assert result is False

    def test_escalation_dry_run(self, mock_amo_client):
        """In dry-run mode, escalation returns True but no PATCH."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=True)
        ctrl.client = mock_instance

        lead = {"id": 1}
        close_deadline = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d")
        with patch.object(MockCls, "get_custom_field_value", side_effect=["Р3 — Средний", close_deadline]):
            with patch("src.microservice.cron_hourly.auto_escalate_priority", return_value=("Р1 — Критический", True, "дедлайн ≤ 48ч")):
                result = ctrl._try_escalate_lead(lead)
        assert result is True
        mock_instance.update_lead.assert_not_called()

    def test_escalation_production(self, mock_amo_client):
        """In production mode, escalation patches lead, renames, adds note, creates task."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance

        lead = {"id": 42, "responsible_user_id": 999}
        close_deadline = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d")
        with patch.object(MockCls, "get_custom_field_value", side_effect=["Р3 — Средний", close_deadline, "ООО Заказчик"]):
            with patch("src.microservice.cron_hourly.auto_escalate_priority", return_value=("Р1 — Критический", True, "дедлайн ≤ 48ч")):
                with patch("src.microservice.cron_hourly.PRIORITY_ENUM_IDS", {"Р1 — Критический": 111}):
                    with patch("src.microservice.cron_hourly.build_lead_name", return_value="Р1 | ООО Заказчик"):
                        with patch("src.microservice.cron_hourly.ESCALATION_NOTE_TEMPLATE", "{old_priority} → {new_priority}: {reason} (deadline: {deadline})"):
                            with patch("src.microservice.cron_hourly.Users") as MockUsers:
                                MockUsers.EMPLOYEE_3_PURCHASE = 888
                                result = ctrl._try_escalate_lead(lead)
        assert result is True
        assert mock_instance.update_lead.call_count == 2
        mock_instance.add_note.assert_called_once()
        mock_instance.create_task.assert_called_once()
        assert ctrl.stats["tasks_created"] == 1

    def test_escalation_with_unix_timestamp_deadline(self, mock_amo_client):
        """Handles deadline as Unix timestamp (int)."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=True)
        ctrl.client = mock_instance

        lead = {"id": 5}
        # Deadline as unix timestamp (close to now)
        ts = int((datetime.now() + timedelta(hours=12)).timestamp())
        with patch.object(MockCls, "get_custom_field_value", side_effect=["Р2 — Высокий", ts]):
            with patch("src.microservice.cron_hourly.auto_escalate_priority", return_value=("Р1 — Критический", True, "дедлайн ≤ 48ч")):
                result = ctrl._try_escalate_lead(lead)
        assert result is True


class TestControlPriorityLeads:
    """Tests for _control_priority_leads and _check_priority_lead."""

    def test_control_priority_leads_iterates_statuses(self, mock_amo_client):
        """Iterates over active statuses and checks leads."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance
        mock_instance.get_leads.return_value = []

        ctrl._control_priority_leads()
        # Should call get_leads for each active status
        assert mock_instance.get_leads.call_count >= 5

    def test_check_priority_lead_not_priority(self, mock_amo_client):
        """Non-priority leads are skipped."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance

        lead = {"id": 1}
        with patch.object(MockCls, "get_custom_field_value", return_value="Р4 — Наблюдаем"):
            with patch("src.microservice.cron_hourly.PRIORITY_CONTROL", ["Р1 — Критический", "Р2 — Высокий"]):
                ctrl._check_priority_lead(lead)
        assert ctrl.stats["overdue_found"] == 0

    def test_check_priority_lead_no_active_tasks(self, mock_amo_client):
        """Priority lead with no active tasks triggers control task."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance
        mock_instance.get_tasks_for_lead.return_value = []

        lead = {"id": 10, "name": "Test Lead"}
        with patch.object(MockCls, "get_custom_field_value", return_value="Р1 — Критический"):
            with patch("src.microservice.cron_hourly.PRIORITY_CONTROL", ["Р1 — Критический", "Р2 — Высокий"]):
                ctrl._check_priority_lead(lead)
        assert ctrl.stats["overdue_found"] == 1
        mock_instance.create_task.assert_called_once()

    def test_check_priority_lead_with_overdue_task(self, mock_amo_client):
        """Priority lead with overdue task triggers control task."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance
        # Task that is overdue (complete_till in the past)
        mock_instance.get_tasks_for_lead.return_value = [
            {"is_completed": False, "complete_till": int(time.time()) - 7200}
        ]

        lead = {"id": 10, "name": "Test Lead"}
        with patch.object(MockCls, "get_custom_field_value", return_value="Р1 — Критический"):
            with patch("src.microservice.cron_hourly.PRIORITY_CONTROL", ["Р1 — Критический", "Р2 — Высокий"]):
                ctrl._check_priority_lead(lead)
        assert ctrl.stats["overdue_found"] == 1

    def test_check_priority_lead_with_active_task_ok(self, mock_amo_client):
        """Priority lead with active non-overdue task is fine."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance
        # Task that is NOT overdue
        mock_instance.get_tasks_for_lead.return_value = [
            {"is_completed": False, "complete_till": int(time.time()) + 7200}
        ]

        lead = {"id": 10, "name": "Test Lead"}
        with patch.object(MockCls, "get_custom_field_value", return_value="Р1 — Критический"):
            with patch("src.microservice.cron_hourly.PRIORITY_CONTROL", ["Р1 — Критический", "Р2 — Высокий"]):
                ctrl._check_priority_lead(lead)
        assert ctrl.stats["overdue_found"] == 0


class TestCreateControlTask:
    """Tests for _create_control_task."""

    def test_creates_task_and_increments_stats(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance
        mock_instance.create_task.return_value = {"id": 999}

        lead = {"id": 5, "name": "Тестовая сделка"}
        ctrl._create_control_task(lead, "Р1", "нет активной задачи")
        mock_instance.create_task.assert_called_once()
        assert ctrl.stats["tasks_created"] == 1

    def test_task_creation_fails_no_increment(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance
        mock_instance.create_task.return_value = None

        lead = {"id": 5, "name": "Тестовая сделка"}
        ctrl._create_control_task(lead, "Р1", "нет активной задачи")
        assert ctrl.stats["tasks_created"] == 0


class TestControlNoNextAction:
    """Tests for _control_no_next_action."""

    def test_finds_leads_without_next_action(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance

        lead = {"id": 20, "responsible_user_id": 777}
        mock_instance.get_leads.return_value = [lead]

        with patch.object(MockCls, "get_custom_field_value", return_value=None):
            ctrl._control_no_next_action()
        assert ctrl.stats["no_next_action"] >= 1
        mock_instance.create_task.assert_called()

    def test_leads_with_next_action_are_ok(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance

        lead = {"id": 20, "responsible_user_id": 777}
        mock_instance.get_leads.return_value = [lead]

        with patch.object(MockCls, "get_custom_field_value", return_value="Позвонить завтра"):
            ctrl._control_no_next_action()
        assert ctrl.stats["no_next_action"] == 0


class TestControlOverdueTasks:
    """Tests for _control_overdue_tasks."""

    def test_no_overdue_tasks(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance
        mock_instance.get_overdue_tasks.return_value = []

        ctrl._control_overdue_tasks()
        mock_instance.create_task.assert_not_called()

    def test_few_overdue_tasks_no_summary(self, mock_amo_client):
        """3 or fewer overdue tasks — no summary task created."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance
        mock_instance.get_overdue_tasks.return_value = [
            {"responsible_user_id": 1, "entity_id": 100},
            {"responsible_user_id": 2, "entity_id": 101},
        ]

        with patch("src.microservice.cron_hourly.Users") as MockUsers:
            MockUsers.MANAGER = 555
            ctrl._control_overdue_tasks()
        mock_instance.create_task.assert_not_called()

    def test_many_overdue_tasks_creates_summary(self, mock_amo_client):
        """>3 overdue tasks creates summary task for manager."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance
        mock_instance.get_overdue_tasks.return_value = [
            {"responsible_user_id": 1, "entity_id": 100},
            {"responsible_user_id": 1, "entity_id": 101},
            {"responsible_user_id": 2, "entity_id": 102},
            {"responsible_user_id": 3, "entity_id": 103},
        ]

        with patch("src.microservice.cron_hourly.Users") as MockUsers:
            MockUsers.MANAGER = 555
            ctrl._control_overdue_tasks()
        mock_instance.create_task.assert_called_once()
        assert ctrl.stats["tasks_created"] == 1

    def test_many_overdue_but_no_entity_id(self, mock_amo_client):
        """>3 overdue tasks but first has no entity_id — no task created."""
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance
        mock_instance.get_overdue_tasks.return_value = [
            {"responsible_user_id": 1, "entity_id": 0},
            {"responsible_user_id": 1, "entity_id": 101},
            {"responsible_user_id": 2, "entity_id": 102},
            {"responsible_user_id": 3, "entity_id": 103},
        ]

        with patch("src.microservice.cron_hourly.Users") as MockUsers:
            MockUsers.MANAGER = 555
            ctrl._control_overdue_tasks()
        mock_instance.create_task.assert_not_called()


class TestEscalateByDeadline:
    """Tests for _escalate_by_deadline."""

    def test_iterates_statuses_and_leads(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=False)
        ctrl.client = mock_instance
        mock_instance.get_leads.return_value = []

        ctrl._escalate_by_deadline()
        assert mock_instance.get_leads.call_count >= 5

    def test_escalates_lead_in_loop(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        from src.microservice.cron_hourly import HourlyControl
        ctrl = HourlyControl(dry_run=True)
        ctrl.client = mock_instance

        lead = {"id": 77}
        mock_instance.get_leads.return_value = [lead]

        close_deadline = (datetime.now() + timedelta(hours=12)).strftime("%Y-%m-%d")
        with patch.object(MockCls, "get_custom_field_value", side_effect=["Р3 — Средний", close_deadline] * 20):
            with patch("src.microservice.cron_hourly.auto_escalate_priority", return_value=("Р1 — Критический", True, "дедлайн ≤ 48ч")):
                ctrl._escalate_by_deadline()
        assert ctrl.stats["escalated"] >= 1


class TestRunHourlyFunction:
    """Tests for the run_hourly entry point."""

    def test_run_hourly_returns_stats(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        mock_instance.get_leads.return_value = []
        mock_instance.get_overdue_tasks.return_value = []

        from src.microservice.cron_hourly import run_hourly
        stats = run_hourly(dry_run=True)
        assert "checked" in stats
        assert "errors" in stats

    def test_run_hourly_handles_exception(self, mock_amo_client):
        MockCls, mock_instance = mock_amo_client
        mock_instance.get_leads.side_effect = Exception("API Error")

        from src.microservice.cron_hourly import run_hourly
        stats = run_hourly(dry_run=True)
        assert stats["errors"] >= 1
