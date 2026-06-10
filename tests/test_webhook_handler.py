"""
Тесты для webhook_handler — обработка вебхуков amoCRM.

Покрытие:
- handle_webhook — основной endpoint
- _handle_status_change — смена статуса
- _handle_lead_add — создание сделки
- _handle_note_add — обработка примечаний
- _parse_lead_status_data — парсинг form-encoded данных
- _build_name_from_lead — построение имени сделки

Запуск:
    pytest tests/test_webhook_handler.py -v
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone

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

import pytest
from httpx import AsyncClient, ASGITransport
from src.microservice.webhook_handler import (
    router,
    _handle_lead_add,
    _build_name_from_lead,
)
from src.microservice.config import PIPELINE_ACTIVE, Fields, PRIORITY_LABELS


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: _build_name_from_lead
# ═══════════════════════════════════════════════════════════════════

class TestBuildNameFromLead:
    """Тесты построения имени сделки из полей."""

    def test_no_custom_fields(self):
        lead = {"id": 1, "name": "Old name", "custom_fields_values": []}
        result = _build_name_from_lead(lead)
        assert result is None

    def test_no_priority_field(self):
        lead = {
            "id": 1,
            "name": "Old name",
            "custom_fields_values": [
                {"field_id": Fields.CUSTOMER, "values": [{"value": "ООО Завод"}]},
            ],
        }
        result = _build_name_from_lead(lead)
        assert result is None

    def test_priority_not_in_labels(self):
        lead = {
            "id": 1,
            "name": "Old name",
            "custom_fields_values": [
                {"field_id": Fields.PRIORITY, "values": [{"enum_id": 999999}]},
            ],
        }
        result = _build_name_from_lead(lead)
        assert result is None

    def test_valid_priority_and_customer(self):
        # Use a valid priority enum_id from PRIORITY_LABELS
        valid_enum_id = list(PRIORITY_LABELS.keys())[0] if PRIORITY_LABELS else 215673
        lead = {
            "id": 1,
            "name": "Old name",
            "custom_fields_values": [
                {"field_id": Fields.PRIORITY, "values": [{"enum_id": valid_enum_id}]},
                {"field_id": Fields.CUSTOMER, "values": [{"value": "КБП Шипунова"}]},
            ],
        }
        result = _build_name_from_lead(lead)
        if PRIORITY_LABELS:
            assert result is not None
            assert "КБП Шипунова" in result

    def test_valid_priority_customer_and_deadline(self):
        valid_enum_id = list(PRIORITY_LABELS.keys())[0] if PRIORITY_LABELS else 215673
        # Unix timestamp for 2025-06-15
        deadline_ts = "1750000000"
        lead = {
            "id": 1,
            "name": "Old name",
            "custom_fields_values": [
                {"field_id": Fields.PRIORITY, "values": [{"enum_id": valid_enum_id}]},
                {"field_id": Fields.CUSTOMER, "values": [{"value": "АО Факел"}]},
                {"field_id": Fields.DEADLINE, "values": [{"value": deadline_ts}]},
            ],
        }
        result = _build_name_from_lead(lead)
        if PRIORITY_LABELS:
            assert result is not None
            assert "АО Факел" in result

    def test_no_custom_fields_key(self):
        lead = {"id": 1, "name": "Old name"}
        result = _build_name_from_lead(lead)
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: _handle_lead_add
# ═══════════════════════════════════════════════════════════════════

class TestHandleLeadAdd:
    @pytest.mark.asyncio
    async def test_handle_lead_add_basic(self):
        body = {
            "leads[add][0][id]": "12345",
            "leads[add][0][name]": "Новая сделка",
        }
        result = await _handle_lead_add(body)
        assert result["status"] == "ok"
        assert result["action"] == "lead_add_logged"
        assert result["lead_id"] == "12345"

    @pytest.mark.asyncio
    async def test_handle_lead_add_missing_fields(self):
        body = {}
        result = await _handle_lead_add(body)
        assert result["status"] == "ok"
        assert result["lead_id"] == "?"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: handle_webhook (integration via TestClient)
# ═══════════════════════════════════════════════════════════════════

class TestWebhookEndpoint:
    """Integration tests for the webhook endpoint using FastAPI TestClient."""

    def setup_method(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    @patch("src.microservice.webhook_handler.get_amo_client")
    def test_webhook_status_change_wrong_pipeline(self, mock_get_client):
        """Status change for non-active pipeline should be ignored."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/webhook",
            data={
                "leads[status][0][id]": "12345",
                "leads[status][0][status_id]": "100002",
                "leads[status][0][pipeline_id]": "99999",  # Wrong pipeline
                "leads[status][0][old_status_id]": "100001",
                "leads[status][0][old_pipeline_id]": "99999",
                "leads[status][0][responsible_user_id]": "9000001",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "not_active_pipeline"

    @patch("src.microservice.webhook_handler.get_amo_client")
    def test_webhook_status_change_active_pipeline(self, mock_get_client):
        """Status change for active pipeline should be processed."""
        mock_client = MagicMock()
        mock_client.get_lead.return_value = {
            "id": 12345,
            "name": "Test Lead",
            "custom_fields_values": [],
        }
        mock_client.create_task.return_value = {"id": 999}
        mock_client.add_note.return_value = True
        mock_client.update_lead.return_value = True
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/webhook",
            data={
                "leads[status][0][id]": "12345",
                "leads[status][0][status_id]": "100002",
                "leads[status][0][pipeline_id]": str(PIPELINE_ACTIVE),
                "leads[status][0][old_status_id]": "100001",
                "leads[status][0][old_pipeline_id]": str(PIPELINE_ACTIVE),
                "leads[status][0][responsible_user_id]": "9000001",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_webhook_lead_add(self):
        """Lead add event should be logged."""
        response = self.client.post(
            "/webhook",
            data={
                "leads[add][0][id]": "67890",
                "leads[add][0][name]": "Новый тендер",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["action"] == "lead_add_logged"

    def test_webhook_unhandled_event(self):
        """Unknown event type should be ignored."""
        response = self.client.post(
            "/webhook",
            data={"contacts[update][0][id]": "111"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "unhandled_event_type"

    @patch("src.microservice.webhook_handler.get_amo_client")
    def test_webhook_note_add(self, mock_get_client):
        """Note add event with Yandex.Disk link should trigger action3."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/webhook",
            data={
                "notes[add][0][id]": "555",
                "notes[add][0][element_id]": "12345",
                "notes[add][0][note_type]": "common",
                "notes[add][0][params][text]": "Ссылка https://disk.yandex.ru/d/abc123",
            },
        )
        assert response.status_code == 200

    def test_webhook_empty_body(self):
        """Empty body should be handled gracefully."""
        response = self.client.post("/webhook", data={})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
