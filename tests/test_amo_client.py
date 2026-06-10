"""
Тесты для AmoClient (src/microservice/amo_client.py).

Покрытие:
- _request — возвращает requests.Response
- get_leads — получение лидов
- get_lead — получение одного лида
- update_lead — обновление лида
- create_task — создание задачи
- add_note — добавление заметки
- move_lead — перемещение лида
- get_custom_field_value — извлечение значения поля
- build_custom_fields_payload — формирование payload

Запуск:
    pytest tests/test_amo_client.py -v
"""

import os
import sys
import json
import time
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.microservice.amo_client import AmoClient


def _make_response(status_code=200, json_data=None, text=""):
    """Создать mock Response объект."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


@pytest.fixture
def client():
    return AmoClient(dry_run=True)


@pytest.fixture
def live_client():
    return AmoClient(dry_run=False)


@pytest.fixture
def sample_lead():
    return {
        "id": 1001,
        "name": "[P1] — Тест",
        "status_id": 100005,
        "custom_fields_values": [
            {"field_id": 380309, "values": [{"value": "Р1", "enum_id": 215673}]},
            {"field_id": 380317, "values": [{"value": "2025-07-15"}]},
            {"field_id": 380299, "values": [{"value": "ООО Тест"}]},
        ],
    }


class TestInit:
    def test_init_dry_run(self, client):
        assert client.dry_run is True

    def test_init_live(self, live_client):
        assert live_client.dry_run is False

    def test_init_sets_base_url(self, client):
        assert "tokutools" in client.base_url


class TestRequest:
    @patch("src.microservice.amo_client.requests.request")
    def test_get_success(self, mock_req, live_client):
        mock_req.return_value = _make_response(200, {"data": "test"})
        result = live_client._request("GET", "leads")
        assert result.status_code == 200
        assert result.json() == {"data": "test"}

    @patch("src.microservice.amo_client.requests.request")
    @patch("time.sleep")
    def test_rate_limit_429_retries(self, mock_sleep, mock_req, live_client):
        rate_resp = _make_response(429)
        ok_resp = _make_response(200, {"ok": True})
        mock_req.side_effect = [rate_resp, ok_resp]

        result = live_client._request("GET", "leads")
        assert result.status_code == 200

    @patch("src.microservice.amo_client.requests.request")
    def test_non_server_error_returns(self, mock_req, live_client):
        """401 is returned (not retried) since it's not 429 or 5xx."""
        mock_req.return_value = _make_response(401, text="Unauthorized")
        result = live_client._request("GET", "leads")
        assert result.status_code == 401

    @patch("src.microservice.amo_client.requests.request")
    @patch("time.sleep")
    def test_500_retries_then_returns_none(self, mock_sleep, mock_req, live_client):
        """500 is retried 3 times then returns None."""
        mock_req.return_value = _make_response(500, text="Server Error")
        result = live_client._request("GET", "leads")
        assert result is None

    @patch("src.microservice.amo_client.requests.request")
    @patch("time.sleep")
    def test_timeout_retries(self, mock_sleep, mock_req, live_client):
        import requests
        mock_req.side_effect = requests.exceptions.Timeout("Timed out")
        result = live_client._request("GET", "leads")
        assert result is None

    @patch("src.microservice.amo_client.requests.request")
    @patch("time.sleep")
    def test_connection_error_retries(self, mock_sleep, mock_req, live_client):
        import requests
        mock_req.side_effect = requests.exceptions.ConnectionError("No net")
        result = live_client._request("GET", "leads")
        assert result is None


class TestGetLeads:
    @patch.object(AmoClient, "_request")
    def test_success(self, mock_req, live_client):
        leads_data = {"_embedded": {"leads": [{"id": 1}, {"id": 2}]}}
        mock_req.return_value = _make_response(200, leads_data)
        result = live_client.get_leads()
        assert len(result) == 2

    @patch.object(AmoClient, "_request")
    def test_empty_204(self, mock_req, live_client):
        mock_req.return_value = _make_response(204)
        result = live_client.get_leads()
        assert result == []

    @patch.object(AmoClient, "_request")
    def test_none_response(self, mock_req, live_client):
        mock_req.return_value = None
        result = live_client.get_leads()
        assert result == []

    @patch.object(AmoClient, "_request")
    def test_with_status_filter(self, mock_req, live_client):
        leads_data = {"_embedded": {"leads": [{"id": 1}]}}
        mock_req.return_value = _make_response(200, leads_data)
        result = live_client.get_leads(status_id=100005, pipeline_id=10984442)
        assert len(result) == 1


class TestGetLead:
    @patch.object(AmoClient, "_request")
    def test_success(self, mock_req, live_client, sample_lead):
        mock_req.return_value = _make_response(200, sample_lead)
        result = live_client.get_lead(1001)
        assert result["id"] == 1001

    @patch.object(AmoClient, "_request")
    def test_not_found(self, mock_req, live_client):
        mock_req.return_value = _make_response(404)
        result = live_client.get_lead(9999)
        assert result is None

    @patch.object(AmoClient, "_request")
    def test_none_response(self, mock_req, live_client):
        mock_req.return_value = None
        result = live_client.get_lead(9999)
        assert result is None


class TestUpdateLead:
    @patch.object(AmoClient, "_request")
    def test_success(self, mock_req, live_client):
        mock_req.return_value = _make_response(200, {"_embedded": {"leads": [{"id": 1001}]}})
        result = live_client.update_lead(1001, {"name": "New"})
        assert result is True

    def test_dry_run(self, client):
        result = client.update_lead(1001, {"name": "Test"})
        assert result is True

    @patch.object(AmoClient, "_request")
    def test_failure_400(self, mock_req, live_client):
        mock_req.return_value = _make_response(400, text="Bad Request")
        result = live_client.update_lead(1001, {"name": "Fail"})
        assert result is False

    @patch.object(AmoClient, "_request")
    def test_none_response(self, mock_req, live_client):
        mock_req.return_value = None
        result = live_client.update_lead(1001, {"name": "Fail"})
        assert result is False


class TestCreateTask:
    @patch.object(AmoClient, "_request")
    def test_success(self, mock_req, live_client):
        mock_req.return_value = _make_response(200, {"_embedded": {"tasks": [{"id": 5001}]}})
        result = live_client.create_task(
            lead_id=1001, text="Test", responsible_user_id=9000001, deadline_seconds=3600
        )
        assert result is not None
        assert result["id"] == 5001

    def test_dry_run(self, client):
        result = client.create_task(
            lead_id=1001, text="Test", responsible_user_id=9000001, deadline_seconds=3600
        )
        assert result is not None
        assert result.get("_dry_run") is True

    @patch.object(AmoClient, "_request")
    def test_failure(self, mock_req, live_client):
        mock_req.return_value = _make_response(400)
        result = live_client.create_task(
            lead_id=1001, text="Test", responsible_user_id=9000001, deadline_seconds=3600
        )
        assert result is None


class TestAddNote:
    @patch.object(AmoClient, "_request")
    def test_success(self, mock_req, live_client):
        mock_req.return_value = _make_response(200, {"_embedded": {"notes": [{"id": 9001}]}})
        result = live_client.add_note(lead_id=1001, text="Заметка")
        assert result is not None
        assert result["id"] == 9001

    def test_dry_run(self, client):
        result = client.add_note(lead_id=1001, text="Test")
        assert result is not None
        assert result.get("_dry_run") is True

    @patch.object(AmoClient, "_request")
    def test_failure(self, mock_req, live_client):
        mock_req.return_value = _make_response(400)
        result = live_client.add_note(lead_id=1001, text="Fail")
        assert result is None


class TestMoveLead:
    @patch.object(AmoClient, "_request")
    def test_success(self, mock_req, live_client):
        mock_req.return_value = _make_response(200, {"_embedded": {"leads": [{"id": 1001}]}})
        result = live_client.move_lead(lead_id=1001, pipeline_id=10984454, status_id=200003)
        assert result is True

    def test_dry_run(self, client):
        result = client.move_lead(lead_id=1001, pipeline_id=10984454, status_id=200003)
        assert result is True


class TestStaticMethods:
    def test_get_custom_field_value(self, sample_lead):
        result = AmoClient.get_custom_field_value(sample_lead, 380309)
        assert result == "Р1"

    def test_get_custom_field_value_missing(self, sample_lead):
        result = AmoClient.get_custom_field_value(sample_lead, 999999)
        assert result is None

    def test_get_custom_field_value_no_fields(self):
        lead = {"id": 1, "custom_fields_values": None}
        result = AmoClient.get_custom_field_value(lead, 380309)
        assert result is None

    def test_build_custom_fields_payload(self):
        fields_map = {380309: "Р2", 380317: "2025-08-01"}
        result = AmoClient.build_custom_fields_payload(fields_map)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all("field_id" in f for f in result)

    def test_build_custom_fields_payload_empty(self):
        result = AmoClient.build_custom_fields_payload({})
        assert result == []
