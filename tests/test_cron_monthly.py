"""
Тесты для cron_monthly — ежемесячная ревизия архива.

Покрытие:
- MonthlyRevision.__init__
- MonthlyRevision.run
- MonthlyRevision._audit_archive_directions
- MonthlyRevision._audit_archive_soz
- MonthlyRevision._count_active_priorities
- MonthlyRevision._generate_report
- MonthlyRevision._get_all_pipeline_leads
- run_monthly

Запуск:
    pytest tests/test_cron_monthly.py -v
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call
from datetime import datetime
from collections import Counter

# Устанавливаем переменные окружения ДО импорта
os.environ.setdefault("AMO_DOMAIN", "tokutools.amocrm.ru")
os.environ.setdefault("AMO_ACCESS_TOKEN", "test_token")
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.microservice.cron_monthly import MonthlyRevision, run_monthly


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_archive_lead_no_return_date():
    """Архивная сделка без даты возврата и причины закрытия."""
    return {
        "id": 1001,
        "name": "Тестовая сделка без даты",
        "custom_fields_values": [
            {"field_id": 388155, "values": [{"value": "HSS-06 — Спец. быстрорез по чертежам"}]},
        ],
        "responsible_user_id": 9000001,
    }


@pytest.fixture
def sample_archive_lead_complete():
    """Архивная сделка с заполненными полями."""
    return {
        "id": 1002,
        "name": "Полная сделка",
        "custom_fields_values": [
            {"field_id": 388155, "values": [{"value": "HSS-01 — Каталожный быстрорез ГОСТ"}]},
            {"field_id": 388159, "values": [{"value": "Проиграли по цене"}]},
            {"field_id": 388165, "values": [{"value": "1735689600"}]},
        ],
        "responsible_user_id": 9000001,
    }


@pytest.fixture
def sample_active_lead_p1():
    """Активная сделка с приоритетом Р1."""
    return {
        "id": 2001,
        "name": "[P1] СРОЧНО — Завод",
        "custom_fields_values": [
            {"field_id": 388147, "values": [{"value": "Р1 — Срочно"}]},
        ],
    }


@pytest.fixture
def sample_active_lead_p2():
    """Активная сделка с приоритетом Р2."""
    return {
        "id": 2002,
        "name": "[P2] Быстрые деньги",
        "custom_fields_values": [
            {"field_id": 388147, "values": [{"value": "Р2 — Быстрые деньги"}]},
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: MonthlyRevision
# ═══════════════════════════════════════════════════════════════════

class TestMonthlyRevisionInit:
    @patch("src.microservice.cron_monthly.AmoClient")
    def test_init_dry_run(self, mock_cls):
        mr = MonthlyRevision(dry_run=True)
        assert mr.dry_run is True
        assert mr.report["date"] == datetime.now().strftime("%d.%m.%Y")
        assert mr.report["archive_directions_total"] == 0
        assert mr.report["archive_soz_total"] == 0
        assert mr.report["active_total"] == 0

    @patch("src.microservice.cron_monthly.AmoClient")
    def test_init_not_dry_run(self, mock_cls):
        mr = MonthlyRevision(dry_run=False)
        assert mr.dry_run is False


class TestMonthlyRevisionRun:
    @patch("src.microservice.cron_monthly.AmoClient")
    def test_run_empty_pipelines(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_leads.return_value = []
        mock_cls.return_value = mock_client

        mr = MonthlyRevision(dry_run=True)
        result = mr.run()

        assert isinstance(result, dict)
        assert result["archive_directions_total"] == 0
        assert result["archive_soz_total"] == 0
        assert result["active_total"] == 0

    @patch("src.microservice.cron_monthly.AmoClient")
    def test_run_with_archive_leads(
        self, mock_cls, sample_archive_lead_no_return_date, sample_archive_lead_complete
    ):
        mock_client = MagicMock()
        # get_leads for archive directions (paginated)
        mock_client.get_leads.side_effect = [
            [sample_archive_lead_no_return_date, sample_archive_lead_complete],
            [],  # end of pagination for directions
            [],  # archive SOZ
            [],  # active pipeline
        ]
        mock_client.create_task.return_value = True
        mock_client.add_note.return_value = True
        mock_cls.return_value = mock_client

        mr = MonthlyRevision(dry_run=False)
        result = mr.run()

        assert isinstance(result, dict)
        assert result["archive_directions_total"] == 2

    @patch("src.microservice.cron_monthly.AmoClient")
    def test_run_with_active_leads_priorities(
        self, mock_cls, sample_active_lead_p1, sample_active_lead_p2
    ):
        mock_client = MagicMock()
        mock_client.get_leads.side_effect = [
            [],  # archive directions
            [],  # archive SOZ
            [sample_active_lead_p1, sample_active_lead_p2],  # active
            [],  # end of active pagination
        ]
        mock_client.create_task.return_value = True
        mock_client.add_note.return_value = True
        mock_cls.return_value = mock_client

        mr = MonthlyRevision(dry_run=False)
        result = mr.run()

        assert result["active_total"] == 2

    @patch("src.microservice.cron_monthly.AmoClient")
    def test_run_exception_handled(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_leads.side_effect = Exception("API Error")
        mock_cls.return_value = mock_client

        mr = MonthlyRevision(dry_run=True)
        # Should not raise
        result = mr.run()
        assert isinstance(result, dict)


class TestGetAllPipelineLeads:
    @patch("src.microservice.cron_monthly.AmoClient")
    def test_single_page(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_leads.side_effect = [
            [{"id": 1}, {"id": 2}],
            [],  # end
        ]
        mock_cls.return_value = mock_client

        mr = MonthlyRevision(dry_run=True)
        leads = mr._get_all_pipeline_leads(10984442)
        assert len(leads) == 2

    @patch("src.microservice.cron_monthly.AmoClient")
    def test_multiple_pages(self, mock_cls):
        mock_client = MagicMock()
        # Simulate 250 leads per page (full page), then partial page
        page1 = [{"id": i} for i in range(250)]
        page2 = [{"id": i} for i in range(250, 260)]
        mock_client.get_leads.side_effect = [page1, page2]
        mock_cls.return_value = mock_client

        mr = MonthlyRevision(dry_run=True)
        leads = mr._get_all_pipeline_leads(10984442)
        assert len(leads) == 260

    @patch("src.microservice.cron_monthly.AmoClient")
    def test_empty_pipeline(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_leads.return_value = []
        mock_cls.return_value = mock_client

        mr = MonthlyRevision(dry_run=True)
        leads = mr._get_all_pipeline_leads(10984442)
        assert leads == []


class TestGenerateReport:
    @patch("src.microservice.cron_monthly.AmoClient")
    @patch("src.microservice.cron_monthly.Users")
    def test_report_with_problems(self, mock_users, mock_cls):
        mock_users.MANAGER = 9000003
        mock_client = MagicMock()
        mock_client.get_leads.return_value = [{"id": 1}]
        mock_client.create_task.return_value = True
        mock_client.add_note.return_value = True
        mock_cls.return_value = mock_client

        mr = MonthlyRevision(dry_run=False)
        mr.report["no_return_date"] = [
            {"id": 1001, "name": "Проблемная сделка 1"},
            {"id": 1002, "name": "Проблемная сделка 2"},
        ]
        mr.report["no_close_reason"] = [{"id": 1003, "name": "Без причины"}]
        mr.report["active_total"] = 10
        mr.report["archive_directions_total"] = 5

        mr._generate_report()

        # Should create task for manager
        mock_client.create_task.assert_called()
        mock_client.add_note.assert_called()

    @patch("src.microservice.cron_monthly.AmoClient")
    @patch("src.microservice.cron_monthly.Users")
    def test_report_no_problems(self, mock_users, mock_cls):
        mock_users.MANAGER = 9000003
        mock_client = MagicMock()
        mock_client.get_leads.return_value = [{"id": 1}]
        mock_client.create_task.return_value = True
        mock_client.add_note.return_value = True
        mock_cls.return_value = mock_client

        mr = MonthlyRevision(dry_run=False)
        mr.report["active_total"] = 5
        mr.report["archive_directions_total"] = 3

        mr._generate_report()
        mock_client.create_task.assert_called()


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: run_monthly
# ═══════════════════════════════════════════════════════════════════

class TestRunMonthly:
    @patch("src.microservice.cron_monthly.AmoClient")
    def test_run_monthly_function(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_leads.return_value = []
        mock_cls.return_value = mock_client

        result = run_monthly(dry_run=True)
        assert isinstance(result, dict)

    @patch("src.microservice.cron_monthly.AmoClient")
    def test_run_monthly_dry_run(self, mock_cls):
        mock_client = MagicMock()
        mock_client.get_leads.return_value = []
        mock_cls.return_value = mock_client

        result = run_monthly(dry_run=True)
        assert isinstance(result, dict)
        mock_cls.assert_called_once_with(dry_run=True)
