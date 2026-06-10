"""
Глубокие тесты для application-слоя:
- src/application/webhook_service.py (WebhookService.handle_lead_add)
- src/application/cron_service.py (CronService.check_deadlines_and_escalate)
- src/application/deduplication_service.py (DeduplicationService)
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

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


# ═══════════════════════════════════════════════════════════════
# WebhookService Tests
# ═══════════════════════════════════════════════════════════════

class TestWebhookServiceHandleLeadAdd:
    """Tests for WebhookService.handle_lead_add."""

    @pytest.fixture
    def service(self):
        mock_amo = MagicMock()
        from src.application.webhook_service import WebhookService
        svc = WebhookService(amo_client=mock_amo)
        return svc, mock_amo

    def test_lead_not_found(self, service):
        svc, mock_amo = service
        mock_amo.get_lead.return_value = None
        result = svc.handle_lead_add(42)
        assert result == {"status": "error", "reason": "lead_not_found"}

    def test_wrong_status_ignored(self, service):
        svc, mock_amo = service
        mock_amo.get_lead.return_value = {"id": 42, "status_id": 999999}
        result = svc.handle_lead_add(42)
        assert result == {"status": "ignored", "reason": "wrong_status"}

    def test_missing_routing_fields(self, service):
        svc, mock_amo = service
        from src.domain.enums import ActiveStatuses
        mock_amo.get_lead.return_value = {
            "id": 42,
            "status_id": ActiveStatuses.LLM_RECOGNIZED,
            "custom_fields_values": []
        }
        result = svc.handle_lead_add(42)
        assert result == {"status": "ignored", "reason": "missing_routing_fields"}

    def test_successful_routing(self, service):
        svc, mock_amo = service
        from src.domain.enums import ActiveStatuses, Fields
        mock_amo.get_lead.return_value = {
            "id": 42,
            "status_id": ActiveStatuses.LLM_RECOGNIZED,
            "custom_fields_values": [
                {"field_id": Fields.PRIORITY, "values": [{"value": "Р1 — Критический"}]},
                {"field_id": Fields.SITUATION_TYPE, "values": [{"value": "Стандарт"}]},
            ]
        }
        mock_amo.update_lead.return_value = True

        with patch("src.application.webhook_service.resolve_routing", return_value=(100002, 999)):
            result = svc.handle_lead_add(42)
        assert result == {"status": "ok", "action": "routed"}
        mock_amo.update_lead.assert_called_once_with(
            lead_id=42, status_id=100002, responsible_user_id=999
        )

    def test_successful_routing_with_note(self, service):
        svc, mock_amo = service
        from src.domain.enums import ActiveStatuses, Fields
        mock_amo.get_lead.return_value = {
            "id": 42,
            "status_id": ActiveStatuses.LLM_RECOGNIZED,
            "custom_fields_values": [
                {"field_id": Fields.PRIORITY, "values": [{"value": "Р2 — Высокий"}]},
                {"field_id": Fields.SITUATION_TYPE, "values": [{"value": "СОЗ"}]},
            ]
        }
        mock_amo.update_lead.return_value = True
        # Mock status_notes to have a note for the target status
        svc.status_notes = {100003: "Переведено в СОЗ"}

        with patch("src.application.webhook_service.resolve_routing", return_value=(100003, 888)):
            result = svc.handle_lead_add(42)
        assert result == {"status": "ok", "action": "routed"}
        mock_amo.add_note.assert_called_once_with(42, "Переведено в СОЗ")

    def test_update_lead_fails(self, service):
        svc, mock_amo = service
        from src.domain.enums import ActiveStatuses, Fields
        mock_amo.get_lead.return_value = {
            "id": 42,
            "status_id": ActiveStatuses.LLM_RECOGNIZED,
            "custom_fields_values": [
                {"field_id": Fields.PRIORITY, "values": [{"value": "Р1 — Критический"}]},
                {"field_id": Fields.SITUATION_TYPE, "values": [{"value": "Стандарт"}]},
            ]
        }
        mock_amo.update_lead.return_value = False

        with patch("src.application.webhook_service.resolve_routing", return_value=(100002, 999)):
            result = svc.handle_lead_add(42)
        assert result == {"status": "ok", "action": "routed"}
        # Note should NOT be added if update fails
        mock_amo.add_note.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# CronService Tests
# ═══════════════════════════════════════════════════════════════

class TestCronService:
    """Tests for CronService.check_deadlines_and_escalate."""

    @pytest.fixture
    def service(self):
        mock_amo = MagicMock()
        from src.application.cron_service import CronService
        svc = CronService(amo_client=mock_amo)
        return svc, mock_amo

    def test_no_leads(self, service):
        svc, mock_amo = service
        mock_amo.get_leads.return_value = []
        svc.check_deadlines_and_escalate()
        # Should not crash

    def test_lead_in_archive_status_skipped(self, service):
        svc, mock_amo = service
        from src.domain.enums import ActiveStatuses
        mock_amo.get_leads.return_value = [
            {"id": 1, "status_id": ActiveStatuses.TO_ARCHIVE, "custom_fields_values": []}
        ]
        svc.check_deadlines_and_escalate()
        mock_amo.update_lead.assert_not_called()

    @patch("src.application.cron_service.Fields")
    def test_lead_without_priority_skipped(self, mock_fields, service):
        svc, mock_amo = service
        mock_fields.PRIORITY = 999
        mock_fields.DEADLINE = 998
        mock_amo.get_leads.return_value = [
            {"id": 1, "status_id": 100002, "custom_fields_values": [
                {"field_id": 998, "values": [{"value": "2025-07-01"}]}
            ]}
        ]
        svc.check_deadlines_and_escalate()
        mock_amo.update_lead.assert_not_called()

    @patch("src.application.cron_service.Fields")
    def test_lead_without_deadline_skipped(self, mock_fields, service):
        svc, mock_amo = service
        mock_fields.PRIORITY = 999
        mock_fields.DEADLINE = 998
        mock_amo.get_leads.return_value = [
            {"id": 1, "status_id": 100002, "custom_fields_values": [
                {"field_id": 999, "values": [{"value": "Р2 — Высокий"}]}
            ]}
        ]
        svc.check_deadlines_and_escalate()
        mock_amo.update_lead.assert_not_called()

    @patch("src.application.cron_service.Fields")
    def test_lead_escalated(self, mock_fields, service):
        svc, mock_amo = service
        mock_fields.PRIORITY = 999
        mock_fields.DEADLINE = 998
        mock_amo.get_leads.return_value = [
            {"id": 1, "status_id": 100002, "custom_fields_values": [
                {"field_id": 999, "values": [{"value": "Р3 — Средний"}]},
                {"field_id": 998, "values": [{"value": "2025-06-01"}]},
            ]}
        ]

        with patch("src.application.cron_service.auto_escalate_priority", return_value=("Р1 — Критический", "дедлайн ≤ 48ч")):
            svc.check_deadlines_and_escalate()
        mock_amo.update_lead.assert_called_once()
        mock_amo.add_note.assert_called_once()

    @patch("src.application.cron_service.Fields")
    def test_lead_no_escalation_needed(self, mock_fields, service):
        svc, mock_amo = service
        mock_fields.PRIORITY = 999
        mock_fields.DEADLINE = 998
        mock_amo.get_leads.return_value = [
            {"id": 1, "status_id": 100002, "custom_fields_values": [
                {"field_id": 999, "values": [{"value": "Р3 — Средний"}]},
                {"field_id": 998, "values": [{"value": "2025-12-01"}]},
            ]}
        ]

        with patch("src.application.cron_service.auto_escalate_priority", return_value=("Р3 — Средний", "")):
            svc.check_deadlines_and_escalate()
        mock_amo.update_lead.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# DeduplicationService Tests
# ═══════════════════════════════════════════════════════════════

class TestDeduplicationService:
    """Tests for DeduplicationService."""

    @pytest.fixture
    def service(self):
        mock_amo = MagicMock()
        from src.application.deduplication_service import DeduplicationService
        svc = DeduplicationService(amo_client=mock_amo)
        return svc, mock_amo

    def test_check_duplicate_no_match(self, service):
        svc, mock_amo = service
        mock_amo.get_leads.return_value = []

        from src.domain.models import TenderFile
        tf = TenderFile(filename="doc.pdf", file_hash="abc123", source_path="/tmp/doc.pdf")
        result = svc.check_duplicate(tf)
        assert result.is_new is True
        assert result.is_exact_duplicate is False

    def test_check_duplicate_found(self, service):
        svc, mock_amo = service
        from src.domain.enums import Fields
        mock_amo.get_leads.return_value = [
            {
                "id": 99,
                "custom_fields_values": [
                    {"field_id": Fields.FILE_HASH, "values": [{"value": "abc123"}]}
                ]
            }
        ]

        from src.domain.models import TenderFile
        tf = TenderFile(filename="doc.pdf", file_hash="abc123", source_path="/tmp/doc.pdf")
        result = svc.check_duplicate(tf)
        assert result.is_new is False
        assert result.is_exact_duplicate is True
        assert result.existing_lead_id == 99

    def test_check_duplicate_different_hash(self, service):
        svc, mock_amo = service
        from src.domain.enums import Fields
        mock_amo.get_leads.return_value = [
            {
                "id": 99,
                "custom_fields_values": [
                    {"field_id": Fields.FILE_HASH, "values": [{"value": "different_hash"}]}
                ]
            }
        ]

        from src.domain.models import TenderFile
        tf = TenderFile(filename="doc.pdf", file_hash="abc123", source_path="/tmp/doc.pdf")
        result = svc.check_duplicate(tf)
        assert result.is_new is True

    def test_process_new_file_duplicate(self, service):
        svc, mock_amo = service
        from src.domain.enums import Fields
        mock_amo.get_leads.return_value = [
            {
                "id": 99,
                "custom_fields_values": [
                    {"field_id": Fields.FILE_HASH, "values": [{"value": "abc123"}]}
                ]
            }
        ]

        from src.domain.models import TenderFile
        tf = TenderFile(filename="doc.pdf", file_hash="abc123", source_path="/tmp/doc.pdf")
        result = svc.process_new_file(tf)
        assert result == 99
        mock_amo.add_note.assert_called_once()

    def test_process_new_file_unique(self, service):
        svc, mock_amo = service
        mock_amo.get_leads.return_value = []

        from src.domain.models import TenderFile
        tf = TenderFile(filename="doc.pdf", file_hash="unique123", source_path="/tmp/doc.pdf")
        result = svc.process_new_file(tf)
        assert result is None
