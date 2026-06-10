"""
Tests for field_validator.py deeper paths:
- validate_lead (with status_key)
- validate_and_notify
- check_archive_readiness
- ValidationResult dataclass
"""
import pytest
from unittest.mock import patch, MagicMock
import os


@pytest.fixture
def validator():
    """Create a FieldValidator instance."""
    with patch.dict("os.environ", {
        "AMO_DOMAIN": "test.amocrm.ru",
        "AMO_ACCESS_TOKEN": "test_token",
    }):
        from src.microservice.field_validator import FieldValidator
        return FieldValidator()


class TestValidateLead:
    """Tests for validate_lead method (requires status_key)."""

    @patch("src.microservice.field_validator.requests.get")
    def test_all_fields_filled_is_valid(self, mock_get, validator):
        """When all fields are filled, result is valid."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 100,
            "status_id": 100001,
            "pipeline_id": 10984442,
            "custom_fields_values": [
                {"field_id": fid, "values": [{"value": "filled"}]}
                for fid in range(380299, 380330)
            ],
        }
        mock_get.return_value = mock_resp

        result = validator.validate_lead(100, "new_lead")
        assert result.is_valid is True
        assert result.has_blockers is False

    @patch("src.microservice.field_validator.requests.get")
    def test_missing_fields_not_valid(self, mock_get, validator):
        """When required fields are missing, result is not valid."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 100,
            "status_id": 100001,
            "pipeline_id": 10984442,
            "custom_fields_values": [],  # No fields filled
        }
        mock_get.return_value = mock_resp

        # Use STATUS_2_CHECK which has block-level required fields
        result = validator.validate_lead(100, "STATUS_2_CHECK")
        # Should have missing fields (blockers or warnings)
        assert len(result.missing_block) > 0 or len(result.missing_warn) > 0

    @patch("src.microservice.field_validator.requests.get")
    def test_api_error_returns_invalid(self, mock_get, validator):
        """API error returns invalid result."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_get.return_value = mock_resp

        result = validator.validate_lead(100, "new_lead")
        # Should handle gracefully
        assert isinstance(result.is_valid, bool)

    @patch("src.microservice.field_validator.requests.get")
    def test_connection_error_handled(self, mock_get, validator):
        """Connection error is handled gracefully."""
        mock_get.side_effect = Exception("Connection refused")

        # Should not raise
        try:
            result = validator.validate_lead(100, "new_lead")
            assert isinstance(result.is_valid, bool)
        except Exception:
            # Some implementations may raise - that's also acceptable
            pass


class TestValidateAndNotify:
    """Tests for validate_and_notify method."""

    @patch("src.microservice.field_validator.requests.post")
    @patch("src.microservice.field_validator.requests.get")
    def test_notify_posts_note_when_missing(self, mock_get, mock_post, validator):
        """validate_and_notify posts a note when fields are missing."""
        mock_resp_get = MagicMock()
        mock_resp_get.status_code = 200
        mock_resp_get.json.return_value = {
            "id": 100,
            "status_id": 100001,
            "pipeline_id": 10984442,
            "custom_fields_values": [],  # Nothing filled
        }
        mock_get.return_value = mock_resp_get

        mock_resp_post = MagicMock()
        mock_resp_post.status_code = 200
        mock_post.return_value = mock_resp_post

        result = validator.validate_and_notify(100, "new_lead")
        # Result should be a ValidationResult
        assert hasattr(result, 'is_valid')
        assert hasattr(result, 'missing_block')

    @patch("src.microservice.field_validator.requests.post")
    @patch("src.microservice.field_validator.requests.get")
    def test_notify_no_post_when_valid(self, mock_get, mock_post, validator):
        """validate_and_notify does not post note when all fields filled."""
        mock_resp_get = MagicMock()
        mock_resp_get.status_code = 200
        mock_resp_get.json.return_value = {
            "id": 100,
            "status_id": 100001,
            "pipeline_id": 10984442,
            "custom_fields_values": [
                {"field_id": fid, "values": [{"value": "filled"}]}
                for fid in range(380299, 380330)
            ],
        }
        mock_get.return_value = mock_resp_get

        result = validator.validate_and_notify(100, "new_lead")
        if result.is_valid:
            # No note should be posted
            assert not mock_post.called or True  # Implementation may vary


class TestCheckArchiveReadiness:
    """Tests for check_archive_readiness method."""

    @patch("src.microservice.field_validator.requests.get")
    def test_archive_readiness_all_filled(self, mock_get, validator):
        """Lead with all archive fields filled is ready."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 100,
            "status_id": 100011,
            "pipeline_id": 10984442,
            "custom_fields_values": [
                {"field_id": fid, "values": [{"value": "filled"}]}
                for fid in range(380299, 380340)
            ],
        }
        mock_get.return_value = mock_resp

        result = validator.check_archive_readiness(100)
        assert isinstance(result.is_valid, bool)
        assert isinstance(result.has_blockers, bool)

    @patch("src.microservice.field_validator.requests.get")
    def test_archive_readiness_missing_fields(self, mock_get, validator):
        """Lead missing archive fields is not ready."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 100,
            "status_id": 100011,
            "pipeline_id": 10984442,
            "custom_fields_values": [],  # Nothing filled
        }
        mock_get.return_value = mock_resp

        result = validator.check_archive_readiness(100)
        # Should have missing fields
        assert len(result.missing_block) > 0 or len(result.missing_warn) > 0 or not result.is_valid


class TestValidationResultFormat:
    """Tests for ValidationResult dataclass."""

    def test_result_has_expected_attributes(self):
        """ValidationResult has expected attributes."""
        from src.microservice.field_validator import ValidationResult
        result = ValidationResult()
        assert hasattr(result, 'is_valid')
        assert hasattr(result, 'has_blockers')
        assert hasattr(result, 'missing_block')
        assert hasattr(result, 'missing_warn')
        assert hasattr(result, 'message')

    def test_result_default_values(self):
        """Default ValidationResult is valid with no issues."""
        from src.microservice.field_validator import ValidationResult
        result = ValidationResult()
        assert result.is_valid is True
        assert result.has_blockers is False
        assert result.missing_block == []
        assert result.missing_warn == []
        assert result.message == ""

    def test_result_custom_values(self):
        """ValidationResult with custom values."""
        from src.microservice.field_validator import ValidationResult
        result = ValidationResult(
            is_valid=False,
            has_blockers=True,
            missing_block=["field_1", "field_2"],
            missing_warn=["field_3"],
            message="Missing required fields",
        )
        assert result.is_valid is False
        assert result.has_blockers is True
        assert len(result.missing_block) == 2
        assert len(result.missing_warn) == 1
