"""
Tests for amo_client.py methods not covered by existing tests:
- get_all_leads_in_status (pagination logic)
- create_lead (success/failure)
- get_tasks_for_lead
- get_overdue_tasks
- get_users
- get_pipelines
- subscribe_webhook
- list_webhooks
"""
import pytest
import time
from unittest.mock import patch, MagicMock, PropertyMock
from src.microservice.amo_client import AmoClient


@pytest.fixture
def client():
    """Create a live (non-dry-run) AmoClient with mocked env."""
    with patch.dict("os.environ", {
        "AMO_DOMAIN": "test.amocrm.ru",
        "AMO_ACCESS_TOKEN": "test_token",
    }):
        c = AmoClient(dry_run=False)
        return c


@pytest.fixture
def dry_client():
    """Create a dry-run AmoClient."""
    with patch.dict("os.environ", {
        "AMO_DOMAIN": "test.amocrm.ru",
        "AMO_ACCESS_TOKEN": "test_token",
    }):
        c = AmoClient(dry_run=True)
        return c


class TestGetAllLeadsInStatus:
    """Tests for get_all_leads_in_status pagination logic."""

    @patch.object(AmoClient, "get_leads")
    def test_single_page(self, mock_get_leads, client):
        """Single page of results (< 250 leads)."""
        mock_get_leads.return_value = [{"id": i} for i in range(50)]
        result = client.get_all_leads_in_status(pipeline_id=123, status_id=456)
        assert len(result) == 50
        mock_get_leads.assert_called_once()

    @patch.object(AmoClient, "get_leads")
    def test_multiple_pages(self, mock_get_leads, client):
        """Multiple pages of results."""
        page1 = [{"id": i} for i in range(250)]
        page2 = [{"id": i} for i in range(250, 400)]
        mock_get_leads.side_effect = [page1, page2]
        result = client.get_all_leads_in_status(pipeline_id=123, status_id=456)
        assert len(result) == 400
        assert mock_get_leads.call_count == 2

    @patch.object(AmoClient, "get_leads")
    def test_empty_result(self, mock_get_leads, client):
        """No leads found."""
        mock_get_leads.return_value = []
        result = client.get_all_leads_in_status(pipeline_id=123, status_id=456)
        assert result == []

    @patch.object(AmoClient, "get_leads")
    def test_none_result(self, mock_get_leads, client):
        """get_leads returns None (API error)."""
        mock_get_leads.return_value = None
        result = client.get_all_leads_in_status(pipeline_id=123, status_id=456)
        assert result == []

    @patch.object(AmoClient, "get_leads")
    def test_exactly_250_leads_fetches_next_page(self, mock_get_leads, client):
        """Exactly 250 leads triggers next page fetch."""
        page1 = [{"id": i} for i in range(250)]
        page2 = []
        mock_get_leads.side_effect = [page1, page2]
        result = client.get_all_leads_in_status(pipeline_id=123, status_id=456)
        assert len(result) == 250
        assert mock_get_leads.call_count == 2


class TestCreateLead:
    """Tests for create_lead method."""

    @patch.object(AmoClient, "_request")
    def test_create_lead_success(self, mock_request, client):
        """Successful lead creation returns lead dict."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {"leads": [{"id": 12345, "name": "Test"}]}
        }
        mock_request.return_value = mock_resp
        result = client.create_lead({"name": "Test", "pipeline_id": 123})
        assert result == {"id": 12345, "name": "Test"}

    @patch.object(AmoClient, "_request")
    def test_create_lead_empty_response(self, mock_request, client):
        """Empty leads array in response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"_embedded": {"leads": []}}
        mock_request.return_value = mock_resp
        result = client.create_lead({"name": "Test"})
        assert result is None

    @patch.object(AmoClient, "_request")
    def test_create_lead_error(self, mock_request, client):
        """API error returns None."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_request.return_value = mock_resp
        result = client.create_lead({"name": "Test"})
        assert result is None

    @patch.object(AmoClient, "_request")
    def test_create_lead_none_response(self, mock_request, client):
        """None response (all retries failed) returns None."""
        mock_request.return_value = None
        result = client.create_lead({"name": "Test"})
        assert result is None


class TestGetTasksForLead:
    """Tests for get_tasks_for_lead method."""

    @patch.object(AmoClient, "_request")
    def test_success(self, mock_request, client):
        """Returns list of tasks."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {"tasks": [
                {"id": 1, "text": "Task 1"},
                {"id": 2, "text": "Task 2"},
            ]}
        }
        mock_request.return_value = mock_resp
        result = client.get_tasks_for_lead(lead_id=100)
        assert len(result) == 2
        assert result[0]["text"] == "Task 1"

    @patch.object(AmoClient, "_request")
    def test_empty(self, mock_request, client):
        """No tasks returns empty list."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"_embedded": {"tasks": []}}
        mock_request.return_value = mock_resp
        result = client.get_tasks_for_lead(lead_id=100)
        assert result == []

    @patch.object(AmoClient, "_request")
    def test_none_response(self, mock_request, client):
        """None response returns empty list."""
        mock_request.return_value = None
        result = client.get_tasks_for_lead(lead_id=100)
        assert result == []


class TestGetOverdueTasks:
    """Tests for get_overdue_tasks method."""

    @patch("time.time", return_value=1700000000)
    @patch.object(AmoClient, "_request")
    def test_filters_overdue(self, mock_request, mock_time, client):
        """Returns only tasks with complete_till < now."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {"tasks": [
                {"id": 1, "complete_till": 1699999000},  # overdue
                {"id": 2, "complete_till": 1700001000},  # not overdue
            ]}
        }
        mock_request.return_value = mock_resp
        result = client.get_overdue_tasks()
        assert len(result) == 1
        assert result[0]["id"] == 1

    @patch.object(AmoClient, "_request")
    def test_none_response(self, mock_request, client):
        """None response returns empty list."""
        mock_request.return_value = None
        result = client.get_overdue_tasks()
        assert result == []


class TestGetUsers:
    """Tests for get_users method."""

    @patch.object(AmoClient, "_request")
    def test_success(self, mock_request, client):
        """Returns list of users."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {"users": [
                {"id": 1, "name": "Admin"},
                {"id": 2, "name": "Manager"},
            ]}
        }
        mock_request.return_value = mock_resp
        result = client.get_users()
        assert len(result) == 2

    @patch.object(AmoClient, "_request")
    def test_error(self, mock_request, client):
        """Error returns empty list."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_request.return_value = mock_resp
        result = client.get_users()
        assert result == []


class TestGetPipelines:
    """Tests for get_pipelines method."""

    @patch.object(AmoClient, "_request")
    def test_success(self, mock_request, client):
        """Returns list of pipelines."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {"pipelines": [
                {"id": 1, "name": "Active"},
                {"id": 2, "name": "Archive"},
            ]}
        }
        mock_request.return_value = mock_resp
        result = client.get_pipelines()
        assert len(result) == 2

    @patch.object(AmoClient, "_request")
    def test_error(self, mock_request, client):
        """Error returns empty list."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_request.return_value = mock_resp
        result = client.get_pipelines()
        assert result == []


class TestSubscribeWebhook:
    """Tests for subscribe_webhook method."""

    @patch.object(AmoClient, "_request")
    def test_success(self, mock_request, client):
        """Successful webhook subscription."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 42, "destination": "https://example.com"}
        mock_request.return_value = mock_resp
        result = client.subscribe_webhook("https://example.com", ["add_lead"])
        assert result["id"] == 42

    @patch.object(AmoClient, "_request")
    def test_success_201(self, mock_request, client):
        """201 status also counts as success."""
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 43}
        mock_request.return_value = mock_resp
        result = client.subscribe_webhook("https://example.com", ["update_lead"])
        assert result["id"] == 43

    @patch.object(AmoClient, "_request")
    def test_error(self, mock_request, client):
        """Error returns None."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_request.return_value = mock_resp
        result = client.subscribe_webhook("https://example.com", ["add_lead"])
        assert result is None

    @patch.object(AmoClient, "_request")
    def test_none_response(self, mock_request, client):
        """None response returns None."""
        mock_request.return_value = None
        result = client.subscribe_webhook("https://example.com", ["add_lead"])
        assert result is None

    def test_dry_run(self, dry_client):
        """Dry run returns mock result without API call."""
        result = dry_client.subscribe_webhook("https://example.com", ["add_lead"])
        assert result["_dry_run"] is True


class TestListWebhooks:
    """Tests for list_webhooks method."""

    @patch.object(AmoClient, "_request")
    def test_success(self, mock_request, client):
        """Returns list of webhooks."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {"webhooks": [
                {"id": 1, "destination": "https://a.com"},
                {"id": 2, "destination": "https://b.com"},
            ]}
        }
        mock_request.return_value = mock_resp
        result = client.list_webhooks()
        assert len(result) == 2

    @patch.object(AmoClient, "_request")
    def test_error(self, mock_request, client):
        """Error returns empty list."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_request.return_value = mock_resp
        result = client.list_webhooks()
        assert result == []


class TestCreateTaskExtended:
    """Additional tests for create_task covering dry_run branch."""

    @patch.object(AmoClient, "_request")
    def test_create_task_success_returns_task(self, mock_request, client):
        """Successful task creation returns task dict."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {"tasks": [{"id": 99, "text": "Check"}]}
        }
        mock_request.return_value = mock_resp
        result = client.create_task(
            lead_id=100,
            text="Check",
            responsible_user_id=1,
            deadline_seconds=3600,
        )
        assert result["id"] == 99

    def test_create_task_dry_run(self, dry_client):
        """Dry run returns mock task."""
        result = dry_client.create_task(
            lead_id=100,
            text="Check",
            responsible_user_id=1,
            deadline_seconds=3600,
        )
        assert result["_dry_run"] is True
        assert result["id"] == 0

    @patch.object(AmoClient, "_request")
    def test_create_task_failure(self, mock_request, client):
        """Failed task creation returns None."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_request.return_value = mock_resp
        result = client.create_task(
            lead_id=100,
            text="Check",
            responsible_user_id=1,
            deadline_seconds=3600,
        )
        assert result is None
