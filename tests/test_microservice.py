"""
Тесты микросервиса RETEK amoCRM.

Запуск:
    pytest tests/test_microservice.py -v
    pytest tests/test_microservice.py -v -k "test_webhook"
"""

import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Устанавливаем переменные окружения ДО импорта модулей
os.environ.setdefault("AMO_DOMAIN", "tokutools.amocrm.ru")
os.environ.setdefault("AMO_ACCESS_TOKEN", "test_token_for_testing")
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

from httpx import AsyncClient, ASGITransport
from src.microservice.main import app
from src.microservice.amo_client import AmoClient
from src.microservice.config import (
    PIPELINE_ACTIVE,
    PIPELINE_ARCHIVE_DIRECTIONS,
    PIPELINE_ARCHIVE_SOZ,
    ActiveStatuses,
    ArchiveDirectionsStatuses,
    ArchiveSozStatuses,
    Fields,
    Users,
    get_status_task_rules,
    resolve_routing,
    resolve_archive_destination,
    ARCHIVE_REQUIRED_FIELDS,
)


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ КОНФИГУРАЦИИ
# ═══════════════════════════════════════════════════════════════════

class TestConfig:
    """Тесты конфигурации."""

    def test_pipeline_ids_set(self):
        """Проверяем что ID воронок заданы."""
        assert PIPELINE_ACTIVE == 10984442
        assert PIPELINE_ARCHIVE_DIRECTIONS == 10984454
        assert PIPELINE_ARCHIVE_SOZ == 10985038

    def test_active_statuses_loaded(self):
        """Проверяем что статусы загружены из env."""
        assert ActiveStatuses.LLM_RECOGNIZED == 100001
        assert ActiveStatuses.BIDDING == 100009
        assert ActiveStatuses.PRODUCTION == 100010
        assert ActiveStatuses.TO_ARCHIVE == 100011

    def test_archive_statuses_loaded(self):
        """Проверяем что архивные статусы загружены."""
        assert ArchiveDirectionsStatuses.SPEC_DRAWING == 200001
        assert ArchiveSozStatuses.WAITING_REAL_TENDER == 300001

    def test_users_loaded(self):
        """Проверяем что пользователи загружены."""
        assert Users.EMPLOYEE_2_SALES == 9000001
        assert Users.EMPLOYEE_3_BUYER == 9000002
        assert Users.MANAGER == 9000003

    def test_status_task_rules(self):
        """Проверяем правила создания задач."""
        rules = get_status_task_rules()
        assert len(rules) == 6  # 6 статусов с правилами (добавлен BIDDING)

        # LLM распознал → задача Сотруднику 2
        rule = rules[100001]
        assert "LLM" in rule["text"]
        assert rule["responsible_user_id"] == Users.EMPLOYEE_2_SALES
        assert rule["deadline_seconds"] == 2 * 3600

        # Передано в закупку → задача Сотруднику 3
        rule = rules[100005]
        assert rule["responsible_user_id"] == Users.EMPLOYEE_3_BUYER
        assert rule["deadline_seconds"] == 2 * 24 * 3600

        # Торги → задача ответственному за сделку
        rule = rules[100009]
        assert rule["responsible_user_id"] is None  # _LEAD_RESPONSIBLE
        assert rule["deadline_seconds"] == 24 * 3600

    def test_routing_soz(self):
        """Проверяем маршрутизацию: Р1 + СОЗ → СОЗ-звонок, Сотрудник 2."""
        status_id, user_id = resolve_routing("Р1", "СОЗ")
        assert status_id == ActiveStatuses.SOZ_CALL
        assert user_id == Users.EMPLOYEE_2_SALES

    def test_routing_real_tender(self):
        """Проверяем маршрутизацию: Р2 + Реальные торги → Закупка, Сотрудник 3."""
        status_id, user_id = resolve_routing("Р2", "Запрос котировок / реальные торги")
        assert status_id == ActiveStatuses.PURCHASING
        assert user_id == Users.EMPLOYEE_3_BUYER

    def test_routing_p4(self):
        """Проверяем маршрутизацию: Р4 → К архивированию."""
        status_id, user_id = resolve_routing("Р4", "СОЗ")
        assert status_id == ActiveStatuses.TO_ARCHIVE

    def test_routing_unclear(self):
        """Проверяем маршрутизацию: Неясно → Проверка Сотрудника 2."""
        status_id, user_id = resolve_routing("Р2", "Неясно")
        assert status_id == ActiveStatuses.CHECK_EMPLOYEE2
        assert user_id == Users.EMPLOYEE_2_SALES

    def test_routing_unknown_fallback(self):
        """Проверяем fallback для неизвестной комбинации."""
        status_id, user_id = resolve_routing("Р5", "Что-то новое")
        assert status_id == ActiveStatuses.CHECK_EMPLOYEE2
        assert user_id == Users.EMPLOYEE_2_SALES

    def test_archive_routing_spec_drawing(self):
        """Проверяем архивную маршрутизацию: Специнструмент."""
        pipeline, status = resolve_archive_destination(
            "Архив — направления / Специнструмент по чертежам"
        )
        assert pipeline == PIPELINE_ARCHIVE_DIRECTIONS
        assert status == ArchiveDirectionsStatuses.SPEC_DRAWING

    def test_archive_routing_soz_wait(self):
        """Проверяем архивную маршрутизацию: СОЗ ждём торги."""
        pipeline, status = resolve_archive_destination(
            "Архив — СОЗ / Ждём реальные торги"
        )
        assert pipeline == PIPELINE_ARCHIVE_SOZ
        assert status == ArchiveSozStatuses.WAITING_REAL_TENDER

    def test_archive_routing_unknown(self):
        """Проверяем fallback для неизвестного назначения."""
        pipeline, status = resolve_archive_destination("Неизвестное назначение")
        assert pipeline is None
        assert status is None

    def test_archive_required_fields(self):
        """Проверяем что обязательные поля для архивации заданы."""
        assert len(ARCHIVE_REQUIRED_FIELDS) == 9
        assert Fields.SITUATION_TYPE in ARCHIVE_REQUIRED_FIELDS
        assert Fields.CLOSE_REASON in ARCHIVE_REQUIRED_FIELDS
        assert Fields.ARCHIVE_DEST_FINAL in ARCHIVE_REQUIRED_FIELDS


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ AMO CLIENT
# ═══════════════════════════════════════════════════════════════════

class TestAmoClient:
    """Тесты клиента amoCRM."""

    def test_dry_run_create_lead(self):
        """В dry-run режиме сделка не создаётся."""
        client = AmoClient(dry_run=True)
        result = client.create_lead({"name": "Test Lead"})
        assert result is not None
        assert result.get("_dry_run") is True

    def test_dry_run_create_task(self):
        """В dry-run режиме задача не создаётся."""
        client = AmoClient(dry_run=True)
        result = client.create_task(
            lead_id=123,
            text="Test task",
            responsible_user_id=9000001,
            deadline_seconds=3600,
        )
        assert result is not None
        assert result.get("_dry_run") is True

    def test_dry_run_update_lead(self):
        """В dry-run режиме сделка не обновляется."""
        client = AmoClient(dry_run=True)
        result = client.update_lead(123, {"status_id": 100002})
        assert result is True

    def test_dry_run_add_note(self):
        """В dry-run режиме примечание не добавляется."""
        client = AmoClient(dry_run=True)
        result = client.add_note(123, "Test note")
        assert result is not None
        assert result.get("_dry_run") is True

    def test_get_custom_field_value(self):
        """Тест извлечения значения кастомного поля."""
        lead = {
            "id": 1,
            "custom_fields_values": [
                {
                    "field_id": 380309,
                    "values": [{"value": "Р1"}],
                },
                {
                    "field_id": 380305,
                    "values": [{"value": "СОЗ"}],
                },
            ],
        }
        assert AmoClient.get_custom_field_value(lead, 380309) == "Р1"
        assert AmoClient.get_custom_field_value(lead, 380305) == "СОЗ"
        assert AmoClient.get_custom_field_value(lead, 999999) is None

    def test_get_custom_field_value_empty(self):
        """Тест извлечения из сделки без полей."""
        lead = {"id": 1, "custom_fields_values": None}
        assert AmoClient.get_custom_field_value(lead, 380309) is None

    def test_build_custom_fields_payload(self):
        """Тест построения payload для кастомных полей."""
        payload = AmoClient.build_custom_fields_payload({
            380309: "Р2",
            380305: "СОЗ",
            380311: None,  # None — пропускается
        })
        assert len(payload) == 2
        assert payload[0] == {"field_id": 380309, "values": [{"value": "Р2"}]}
        assert payload[1] == {"field_id": 380305, "values": [{"value": "СОЗ"}]}


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ WEBHOOK HANDLER
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestWebhookHandler:
    """Тесты обработчика вебхуков."""

    async def test_health_check(self):
        """Проверяем health endpoint."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "RETEK" in data["service"]

    async def test_root_endpoint(self):
        """Проверяем корневой endpoint."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "RETEK amoCRM Microservice"
        assert "endpoints" in data

    @patch("src.microservice.webhook_handler.get_amo_client")
    async def test_webhook_status_change(self, mock_get_client):
        """Тест обработки вебхука смены статуса."""
        # Мокаем AmoClient
        mock_client = MagicMock()
        mock_client.create_task.return_value = {"id": 999}
        mock_get_client.return_value = mock_client

        # Формируем данные вебхука (form-encoded)
        form_data = {
            "leads[status][0][id]": "12345",
            "leads[status][0][status_id]": "100001",  # LLM_RECOGNIZED
            "leads[status][0][pipeline_id]": str(PIPELINE_ACTIVE),
            "leads[status][0][old_status_id]": "0",
            "leads[status][0][responsible_user_id]": "9000001",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/webhook", data=form_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["action"] == "task_created"

        # Проверяем что create_task был вызван
        mock_client.create_task.assert_called_once()
        call_kwargs = mock_client.create_task.call_args[1]
        assert call_kwargs["lead_id"] == 12345
        assert "LLM" in call_kwargs["text"]

    async def test_webhook_unknown_event(self):
        """Тест вебхука с неизвестным событием."""
        form_data = {"unknown[event][0][id]": "123"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/webhook", data=form_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"

    async def test_webhook_wrong_pipeline(self):
        """Тест вебхука из другой воронки (игнорируется)."""
        form_data = {
            "leads[status][0][id]": "12345",
            "leads[status][0][status_id]": "100001",
            "leads[status][0][pipeline_id]": "9999999",  # Другая воронка
            "leads[status][0][old_status_id]": "0",
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/webhook", data=form_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"
        assert data["reason"] == "not_active_pipeline"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ CRON МОДУЛЕЙ
# ═══════════════════════════════════════════════════════════════════

class TestCronHourly:
    """Тесты ежечасного контроля."""

    @patch.object(AmoClient, "_request")
    def test_hourly_dry_run(self, mock_request):
        """Ежечасный контроль в dry-run не делает запросов."""
        from src.microservice.cron_hourly import run_hourly

        # Мокаем ответ API — пустой список сделок
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_request.return_value = mock_response

        stats = run_hourly(dry_run=True)
        assert "checked" in stats
        assert "errors" in stats


class TestCronDaily:
    """Тесты ежедневной архивации."""

    def test_validate_fields_all_present(self):
        """Все обязательные поля заполнены."""
        from src.microservice.cron_daily import DailyArchiver

        archiver = DailyArchiver(dry_run=True)

        lead = {
            "id": 1,
            "custom_fields_values": [
                {"field_id": Fields.SITUATION_TYPE, "values": [{"value": "СОЗ"}]},
                {"field_id": Fields.PRIORITY, "values": [{"value": "Р2"}]},
                {"field_id": Fields.DIRECTION, "values": [{"value": "SPEC-DRAWING"}]},
                {"field_id": Fields.SUB_DIRECTION, "values": [{"value": "твердосплав по чертежам"}]},
                {"field_id": Fields.CLOSE_REASON, "values": [{"value": "Ждём реальные торги"}]},
                {"field_id": Fields.ARCHIVE_DEST_LLM, "values": [{"value": "Архив — СОЗ / Ждём реальные торги"}]},
                {"field_id": Fields.ARCHIVE_DEST_FINAL, "values": [{"value": "Архив — СОЗ / Ждём реальные торги"}]},
                {"field_id": Fields.RETURN_DATE, "values": [{"value": "2026-09-01"}]},
                {"field_id": Fields.NEXT_ACTION, "values": [{"value": "Ждать торги"}]},
            ],
        }

        missing = archiver._validate_archive_fields(lead)
        assert missing == []

    def test_validate_fields_missing(self):
        """Не все обязательные поля заполнены."""
        from src.microservice.cron_daily import DailyArchiver

        archiver = DailyArchiver(dry_run=True)

        lead = {
            "id": 1,
            "custom_fields_values": [
                {"field_id": Fields.SITUATION_TYPE, "values": [{"value": "СОЗ"}]},
                # Остальные поля отсутствуют
            ],
        }

        missing = archiver._validate_archive_fields(lead)
        assert len(missing) > 0
        assert "Приоритет" in missing


# ═══════════════════════════════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
