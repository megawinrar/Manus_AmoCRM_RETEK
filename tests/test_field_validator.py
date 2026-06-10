"""
Тесты для field_validator — валидация обязательных полей карточки.

Покрытие:
- ValidationResult — модель данных
- FieldValidator.__init__
- FieldValidator.validate_lead — основная логика валидации
- REQUIRED_FIELDS_BY_STATUS — матрица обязательных полей
- FIELD_IDS — словарь ID полей

Запуск:
    pytest tests/test_field_validator.py -v
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Устанавливаем переменные окружения ДО импорта
os.environ.setdefault("AMO_DOMAIN", "tokutools.amocrm.ru")
os.environ.setdefault("AMO_ACCESS_TOKEN", "test_token")
os.environ.setdefault("YADISK_TOKEN", "test_yadisk_token")
os.environ.setdefault("FIELD_CUSTOMER", "380299")
os.environ.setdefault("FIELD_DIRECTION", "380311")
os.environ.setdefault("FIELD_PRIORITY", "380309")
os.environ.setdefault("FIELD_SITUATION_TYPE", "380305")
os.environ.setdefault("FIELD_NMC", "380315")
os.environ.setdefault("FIELD_PROCEDURE_TYPE", "380307")
os.environ.setdefault("FIELD_DEALER", "380335")
os.environ.setdefault("FIELD_DEADLINE", "380317")
os.environ.setdefault("FIELD_CLOSE_REASON", "380341")
os.environ.setdefault("FIELD_ARCHIVE_FINAL", "380345")
os.environ.setdefault("FIELD_RETURN_DATE", "380347")
os.environ.setdefault("FIELD_PRODUCTION", "380339")
os.environ.setdefault("FIELD_SOURCE", "380293")
os.environ.setdefault("FIELD_DEALER_DECISION", "380337")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.microservice.field_validator import (
    FieldValidator,
    ValidationResult,
    REQUIRED_FIELDS_BY_STATUS,
    FIELD_IDS,
)


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: ValidationResult
# ═══════════════════════════════════════════════════════════════════

class TestValidationResult:
    def test_default_values(self):
        result = ValidationResult()
        assert result.is_valid is True
        assert result.has_blockers is False
        assert result.missing_block == []
        assert result.missing_warn == []
        assert result.message == ""

    def test_custom_values(self):
        result = ValidationResult(
            is_valid=False,
            has_blockers=True,
            missing_block=["Заказчик"],
            missing_warn=["Приоритет"],
            message="Есть блокирующие ошибки",
        )
        assert result.is_valid is False
        assert result.has_blockers is True
        assert len(result.missing_block) == 1
        assert len(result.missing_warn) == 1
        assert "блокирующие" in result.message


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: FIELD_IDS
# ═══════════════════════════════════════════════════════════════════

class TestFieldIds:
    def test_all_field_ids_are_integers(self):
        for key, value in FIELD_IDS.items():
            assert isinstance(value, int), f"FIELD_IDS[{key}] is not int: {type(value)}"

    def test_required_fields_exist(self):
        required_keys = [
            "CUSTOMER", "DIRECTION", "PRIORITY", "SITUATION_TYPE",
            "NMC", "PROCEDURE_TYPE", "DEALER", "DEADLINE",
            "CLOSE_REASON", "ARCHIVE_DEST_FINAL", "RETURN_DATE",
        ]
        for key in required_keys:
            assert key in FIELD_IDS, f"Missing FIELD_IDS key: {key}"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: REQUIRED_FIELDS_BY_STATUS
# ═══════════════════════════════════════════════════════════════════

class TestRequiredFieldsByStatus:
    def test_all_statuses_have_fields(self):
        for status_key, fields in REQUIRED_FIELDS_BY_STATUS.items():
            assert isinstance(fields, list), f"{status_key} fields is not a list"
            assert len(fields) > 0, f"{status_key} has no required fields"

    def test_field_tuples_format(self):
        """Each field tuple should be (field_id, field_name, severity)."""
        for status_key, fields in REQUIRED_FIELDS_BY_STATUS.items():
            for field_tuple in fields:
                assert len(field_tuple) == 3, f"Bad tuple in {status_key}: {field_tuple}"
                field_id, field_name, severity = field_tuple
                assert isinstance(field_id, int), f"field_id not int in {status_key}"
                assert isinstance(field_name, str), f"field_name not str in {status_key}"
                assert severity in ("block", "warn"), f"Bad severity in {status_key}: {severity}"

    def test_status_1_llm_has_warn_only(self):
        """Status 1 (LLM) should only have warnings, not blockers."""
        fields = REQUIRED_FIELDS_BY_STATUS.get("STATUS_1_LLM", [])
        for _, _, severity in fields:
            assert severity == "warn"

    def test_status_11_archive_has_blockers(self):
        """Status 11 (Archive) should have blocking fields."""
        fields = REQUIRED_FIELDS_BY_STATUS.get("STATUS_11_ARCHIVE", [])
        blockers = [f for f in fields if f[2] == "block"]
        assert len(blockers) >= 2


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: FieldValidator
# ═══════════════════════════════════════════════════════════════════

class TestFieldValidator:
    def setup_method(self):
        self.validator = FieldValidator()

    def test_init(self):
        assert self.validator.base_url is not None
        assert self.validator.headers is not None
        assert "Bearer" in self.validator.headers.get("Authorization", "")

    @patch("requests.get")
    def test_validate_lead_all_fields_filled(self, mock_get):
        """Lead with all required fields filled should pass validation."""
        # Mock API response with all fields filled
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "custom_fields_values": [
                {"field_id": FIELD_IDS["CUSTOMER"], "values": [{"value": "ООО Завод"}]},
                {"field_id": FIELD_IDS["DIRECTION"], "values": [{"value": "HSS-06"}]},
                {"field_id": FIELD_IDS["PRIORITY"], "values": [{"value": "Р1"}]},
            ],
        }
        mock_get.return_value = mock_response

        result = self.validator.validate_lead(12345, "STATUS_1_LLM")
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert result.has_blockers is False

    @patch("requests.get")
    def test_validate_lead_missing_block_fields(self, mock_get):
        """Lead missing blocking fields should fail validation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "custom_fields_values": [],  # No fields filled
        }
        mock_get.return_value = mock_response

        result = self.validator.validate_lead(12345, "STATUS_2_CHECK")
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert result.has_blockers is True
        assert len(result.missing_block) > 0

    @patch("requests.get")
    def test_validate_lead_missing_warn_fields(self, mock_get):
        """Lead missing only warn fields should pass but with warnings."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "custom_fields_values": [
                {"field_id": FIELD_IDS["CUSTOMER"], "values": [{"value": "ООО Завод"}]},
                {"field_id": FIELD_IDS["DIRECTION"], "values": [{"value": "HSS-06"}]},
                {"field_id": FIELD_IDS["PRIORITY"], "values": [{"value": "Р1"}]},
                # Missing SITUATION_TYPE (warn)
            ],
        }
        mock_get.return_value = mock_response

        result = self.validator.validate_lead(12345, "STATUS_2_CHECK")
        assert isinstance(result, ValidationResult)
        # Has blockers = False because all block fields are filled
        assert result.has_blockers is False
        # But has warnings
        assert len(result.missing_warn) > 0

    @patch("requests.get")
    def test_validate_lead_unknown_status(self, mock_get):
        """Unknown status key should return valid result (no rules)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "custom_fields_values": [],
        }
        mock_get.return_value = mock_response

        result = self.validator.validate_lead(12345, "UNKNOWN_STATUS")
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True

    @patch("requests.get")
    def test_validate_lead_api_error(self, mock_get):
        """API error should be handled gracefully."""
        mock_get.side_effect = Exception("Connection error")

        result = self.validator.validate_lead(12345, "STATUS_1_LLM")
        assert isinstance(result, ValidationResult)

    @patch("requests.get")
    def test_validate_lead_archive_status(self, mock_get):
        """Archive status validation with missing required fields."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "custom_fields_values": [
                # Missing CLOSE_REASON and ARCHIVE_DEST_FINAL (both block)
                {"field_id": FIELD_IDS["RETURN_DATE"], "values": [{"value": "1735689600"}]},
            ],
        }
        mock_get.return_value = mock_response

        result = self.validator.validate_lead(12345, "STATUS_11_ARCHIVE")
        assert isinstance(result, ValidationResult)
        assert result.has_blockers is True
        assert len(result.missing_block) >= 2
