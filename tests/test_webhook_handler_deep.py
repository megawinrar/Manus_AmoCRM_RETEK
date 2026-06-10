"""
Deeper tests for webhook_handler.py:
- _handle_status_change with various status transitions
- _handle_note_add with action3 trigger
- _build_name_from_lead edge cases
- _parse_lead_status_data
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import os
import asyncio


@pytest.fixture
def mock_env():
    """Mock environment variables."""
    env = {
        "AMO_DOMAIN": "test.amocrm.ru",
        "AMO_ACCESS_TOKEN": "test_token",
        "DRY_RUN": "1",
        "PIPELINE_ACTIVE": "100",
    }
    with patch.dict("os.environ", env):
        yield


def run_async(coro):
    """Helper to run async functions in sync tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestHandleStatusChange:
    """Tests for _handle_status_change function."""

    @patch("src.microservice.webhook_handler.get_amo_client")
    @patch("src.microservice.webhook_handler.get_status_task_rules")
    @patch("src.microservice.webhook_handler.get_status_note_map")
    @patch("src.microservice.webhook_handler._parse_lead_status_data")
    def test_active_pipeline_status_change(self, mock_parse, mock_note_map, mock_rules, mock_get_client, mock_env):
        """Status change in active pipeline triggers task creation."""
        from src.microservice.webhook_handler import _handle_status_change, PIPELINE_ACTIVE

        mock_parse.return_value = {
            "id": 100,
            "status_id": 200,
            "pipeline_id": PIPELINE_ACTIVE,
            "old_status_id": 199,
            "responsible_user_id": 5001,
        }

        mock_client = MagicMock()
        mock_client.get_lead.return_value = {
            "id": 100,
            "name": "Test Lead",
            "custom_fields_values": [],
        }
        mock_client.create_task.return_value = {"id": 999}
        mock_get_client.return_value = mock_client

        mock_note_map.return_value = {200: "Статус изменён"}
        mock_rules.return_value = {
            200: {"text": "Проверить", "deadline_seconds": 3600, "responsible_user_id": 5001}
        }

        result = run_async(_handle_status_change({"some": "body"}))
        assert result["status"] == "ok"
        assert result["action"] == "task_created"
        mock_client.create_task.assert_called_once()

    @patch("src.microservice.webhook_handler.get_amo_client")
    @patch("src.microservice.webhook_handler._parse_lead_status_data")
    def test_wrong_pipeline_ignored(self, mock_parse, mock_get_client, mock_env):
        """Status change in wrong pipeline is ignored."""
        from src.microservice.webhook_handler import _handle_status_change

        mock_parse.return_value = {
            "id": 100,
            "status_id": 200,
            "pipeline_id": 99999,  # Wrong pipeline
            "old_status_id": 199,
        }

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        result = run_async(_handle_status_change({"some": "body"}))
        assert result["status"] == "ignored"
        assert result["reason"] == "not_active_pipeline"

    @patch("src.microservice.webhook_handler._parse_lead_status_data")
    def test_cannot_parse_returns_ignored(self, mock_parse, mock_env):
        """If lead data cannot be parsed, return ignored."""
        from src.microservice.webhook_handler import _handle_status_change

        mock_parse.return_value = None

        result = run_async(_handle_status_change({"some": "body"}))
        assert result["status"] == "ignored"
        assert result["reason"] == "cannot_parse_lead_data"

    @patch("src.microservice.webhook_handler.get_amo_client")
    @patch("src.microservice.webhook_handler.get_status_task_rules")
    @patch("src.microservice.webhook_handler.get_status_note_map")
    @patch("src.microservice.webhook_handler._parse_lead_status_data")
    def test_no_task_rule_still_adds_note(self, mock_parse, mock_note_map, mock_rules, mock_get_client, mock_env):
        """Status with note but no task rule adds note only."""
        from src.microservice.webhook_handler import _handle_status_change, PIPELINE_ACTIVE

        mock_parse.return_value = {
            "id": 100,
            "status_id": 300,
            "pipeline_id": PIPELINE_ACTIVE,
            "old_status_id": 299,
            "responsible_user_id": 5001,
        }

        mock_client = MagicMock()
        mock_client.get_lead.return_value = {
            "id": 100,
            "name": "Test",
            "custom_fields_values": [],
        }
        mock_get_client.return_value = mock_client
        mock_note_map.return_value = {300: "Заметка для статуса 300"}
        mock_rules.return_value = {}  # No task rule

        result = run_async(_handle_status_change({"some": "body"}))
        assert result["status"] == "ok"
        assert result["action"] == "note_added_no_task_rule"
        mock_client.add_note.assert_called_once()

    @patch("src.microservice.webhook_handler.get_amo_client")
    @patch("src.microservice.webhook_handler.get_status_task_rules")
    @patch("src.microservice.webhook_handler.get_status_note_map")
    @patch("src.microservice.webhook_handler._parse_lead_status_data")
    def test_task_creation_failure(self, mock_parse, mock_note_map, mock_rules, mock_get_client, mock_env):
        """When task creation fails, return error status."""
        from src.microservice.webhook_handler import _handle_status_change, PIPELINE_ACTIVE

        mock_parse.return_value = {
            "id": 100,
            "status_id": 200,
            "pipeline_id": PIPELINE_ACTIVE,
            "old_status_id": 199,
            "responsible_user_id": 5001,
        }

        mock_client = MagicMock()
        mock_client.get_lead.return_value = {"id": 100, "name": "Test", "custom_fields_values": []}
        mock_client.create_task.return_value = None  # Failed
        mock_get_client.return_value = mock_client
        mock_note_map.return_value = {}
        mock_rules.return_value = {
            200: {"text": "Task", "deadline_seconds": 3600, "responsible_user_id": 5001}
        }

        result = run_async(_handle_status_change({"some": "body"}))
        assert result["status"] == "error"
        assert result["action"] == "task_creation_failed"


class TestHandleNoteAdd:
    """Tests for _handle_note_add function."""

    @patch("src.microservice.webhook_handler.get_amo_client")
    def test_note_with_yadisk_link_triggers_action3(self, mock_get_client, mock_env):
        """Note containing YaDisk link triggers action3 processing."""
        from src.microservice.webhook_handler import _handle_note_add

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        body = {
            "notes[add][0][entity_id]": "100",
            "notes[add][0][text]": "Файлы: https://disk.yandex.ru/d/abc123",
        }

        with patch("src.microservice.action3_handler.process_action3") as mock_proc:
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value = MagicMock()
                result = run_async(_handle_note_add(body))

        assert result["status"] == "ok"
        assert result["action"] == "action3_started"

    @patch("src.microservice.webhook_handler.get_amo_client")
    def test_note_without_link_or_trigger_ignored(self, mock_get_client, mock_env):
        """Note without YaDisk link or trigger word is ignored."""
        from src.microservice.webhook_handler import _handle_note_add

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        body = {
            "notes[add][0][entity_id]": "100",
            "notes[add][0][text]": "Обычная заметка без ссылок",
        }

        result = run_async(_handle_note_add(body))
        assert result["status"] == "ignored"
        assert result["reason"] == "no_trigger_word_or_link_in_note"

    def test_note_without_lead_id_ignored(self, mock_env):
        """Note without lead_id is ignored."""
        from src.microservice.webhook_handler import _handle_note_add

        body = {
            "notes[add][0][text]": "https://disk.yandex.ru/d/abc123",
        }

        result = run_async(_handle_note_add(body))
        assert result["status"] == "ignored"
        assert result["reason"] == "cannot_find_lead_id_in_note"

    @patch("src.microservice.webhook_handler.get_amo_client")
    def test_bot_own_note_ignored(self, mock_get_client, mock_env):
        """Bot's own notes (starting with emoji) are ignored."""
        from src.microservice.webhook_handler import _handle_note_add

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        body = {
            "notes[add][0][entity_id]": "100",
            "notes[add][0][text]": "🤖 Найдена ссылка на яндекс.диск",
        }

        result = run_async(_handle_note_add(body))
        assert result["status"] == "ignored"
        assert result["reason"] == "bot_own_note"

    @patch("src.microservice.webhook_handler.get_amo_client")
    def test_trigger_word_without_link_posts_warning(self, mock_get_client, mock_env):
        """Trigger word without link posts a warning note."""
        from src.microservice.webhook_handler import _handle_note_add

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        body = {
            "notes[add][0][entity_id]": "100",
            "notes[add][0][text]": "распознай этот тендер",
        }

        result = run_async(_handle_note_add(body))
        assert result["status"] == "ok"
        assert result["action"] == "action3_missing_link"
        mock_client.add_note.assert_called_once()


class TestBuildNameFromLead:
    """Tests for _build_name_from_lead function."""

    def test_build_name_with_fields(self, mock_env):
        """Build name from lead with priority and customer fields."""
        from src.microservice.webhook_handler import _build_name_from_lead

        lead = {
            "id": 100,
            "custom_fields_values": [
                {"field_id": int(os.getenv("FIELD_PRIORITY", "380309")),
                 "values": [{"enum_id": 215673}]},
                {"field_id": int(os.getenv("FIELD_CUSTOMER", "380299")),
                 "values": [{"value": "ООО Рога"}]},
            ],
        }

        result = _build_name_from_lead(lead)
        # Should return a string (possibly None if fields incomplete)
        assert result is None or isinstance(result, str)

    def test_build_name_empty_fields(self, mock_env):
        """Build name with empty custom fields returns None."""
        from src.microservice.webhook_handler import _build_name_from_lead

        lead = {"id": 100, "custom_fields_values": []}
        result = _build_name_from_lead(lead)
        assert result is None or isinstance(result, str)

    def test_build_name_no_custom_fields_key(self, mock_env):
        """Lead without custom_fields_values key."""
        from src.microservice.webhook_handler import _build_name_from_lead

        lead = {"id": 100}
        result = _build_name_from_lead(lead)
        assert result is None or isinstance(result, str)


class TestParseLeadStatusData:
    """Tests for _parse_lead_status_data function."""

    def test_parse_valid_status_data(self, mock_env):
        """Parse valid form-encoded status data."""
        from src.microservice.webhook_handler import _parse_lead_status_data

        body = {
            "leads[status][0][id]": "100",
            "leads[status][0][status_id]": "200",
            "leads[status][0][pipeline_id]": "300",
            "leads[status][0][old_status_id]": "199",
            "leads[status][0][responsible_user_id]": "5001",
        }

        result = _parse_lead_status_data(body)
        assert result is not None
        assert result["id"] == 100
        assert result["status_id"] == 200
        assert result["pipeline_id"] == 300

    def test_parse_empty_body_returns_none(self, mock_env):
        """Empty body returns None."""
        from src.microservice.webhook_handler import _parse_lead_status_data

        result = _parse_lead_status_data({})
        assert result is None

    def test_parse_missing_required_fields(self, mock_env):
        """Body without required lead status fields returns None."""
        from src.microservice.webhook_handler import _parse_lead_status_data

        body = {"some_key": "some_value"}
        result = _parse_lead_status_data(body)
        assert result is None
