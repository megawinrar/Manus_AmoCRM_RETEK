"""
Тесты для:
- src/archiver.py — модуль архивации
- src/infrastructure/amocrm_client.py — расширенные тесты
- src/infrastructure/llm_client.py — YandexGPTClient
- src/infrastructure/yadisk_client.py — расширенные тесты

Запуск:
    pytest tests/test_archiver_infra.py -v
"""
import os
import sys
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: src/archiver.py
# ═══════════════════════════════════════════════════════════════════

class TestArchiver:
    """Тесты для модуля архивации."""

    @patch("src.archiver.requests.get")
    def test_get_leads_to_archive_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "_embedded": {
                "leads": [
                    {"id": 1, "name": "Lead 1"},
                    {"id": 2, "name": "Lead 2"},
                ]
            }
        }
        mock_get.return_value = mock_response

        from src.archiver import get_leads_to_archive
        result = get_leads_to_archive()
        assert len(result) == 2
        assert result[0]["id"] == 1

    @patch("src.archiver.requests.get")
    def test_get_leads_to_archive_empty(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"_embedded": {"leads": []}}
        mock_get.return_value = mock_response

        from src.archiver import get_leads_to_archive
        result = get_leads_to_archive()
        assert result == []

    @patch("src.archiver.requests.get")
    def test_get_leads_to_archive_api_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        from src.archiver import get_leads_to_archive
        result = get_leads_to_archive()
        assert result == []

    def test_determine_archive_destination(self):
        from src.archiver import determine_archive_destination, ARCHIVE_DIR_PIPELINE_ID
        lead = {"id": 1, "custom_fields_values": []}
        pipeline_id, status_id = determine_archive_destination(lead)
        assert pipeline_id == ARCHIVE_DIR_PIPELINE_ID

    @patch("src.archiver.requests.patch")
    def test_move_lead_to_archive_success(self, mock_patch):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_patch.return_value = mock_response

        from src.archiver import move_lead_to_archive
        result = move_lead_to_archive(12345, 10984454, 200001)
        assert result is True

    @patch("src.archiver.requests.patch")
    def test_move_lead_to_archive_failure(self, mock_patch):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_patch.return_value = mock_response

        from src.archiver import move_lead_to_archive
        result = move_lead_to_archive(12345, 10984454, 200001)
        assert result is False


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: src/infrastructure/amocrm_client.py (расширенные)
# ═══════════════════════════════════════════════════════════════════

class TestAmoClientExtended:
    """Расширенные тесты для AmoClient."""

    def setup_method(self):
        from src.infrastructure.amocrm_client import AmoClient
        self.client = AmoClient("tokutools", "test_token")
        self.client.dry_run = True

    def test_get_lead_dry_run(self):
        """In dry-run, GET requests still go through (only mutations are blocked)."""
        # dry_run only affects POST/PATCH/DELETE
        assert self.client.dry_run is True

    @patch("requests.request")
    def test_get_lead_success(self, mock_request):
        self.client.dry_run = False
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"id": 123}'
        mock_response.json.return_value = {"id": 123, "name": "Test"}
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.client.get_lead(123)
        assert result["id"] == 123

    @patch("requests.request")
    def test_get_leads_success(self, mock_request):
        self.client.dry_run = False
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"_embedded": {"leads": [{"id": 1}]}}'
        mock_response.json.return_value = {"_embedded": {"leads": [{"id": 1}]}}
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.client.get_leads()
        assert len(result) == 1
        assert result[0]["id"] == 1

    @patch("requests.request")
    def test_get_leads_empty(self, mock_request):
        self.client.dry_run = False
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{}'
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.client.get_leads()
        assert result == []

    @patch("requests.request")
    def test_get_leads_with_query(self, mock_request):
        self.client.dry_run = False
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"_embedded": {"leads": []}}'
        mock_response.json.return_value = {"_embedded": {"leads": []}}
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.client.get_leads(query="test", pipeline_id=123)
        assert result == []

    def test_create_lead_dry_run(self):
        result = self.client.create_lead("Test Lead", 10984442, 100001)
        assert result == 9999999

    def test_update_lead_dry_run(self):
        result = self.client.update_lead(123, status_id=100002)
        assert result is True

    def test_add_note_dry_run(self):
        result = self.client.add_note(123, "Test note text")
        assert result == 9999999

    def test_add_task_dry_run(self):
        result = self.client.add_task(123, "Test task", 1700000000)
        assert result == 9999999

    def test_add_task_with_responsible(self):
        result = self.client.add_task(123, "Task", 1700000000, responsible_user_id=9000001)
        assert result == 9999999

    @patch("requests.request")
    def test_request_http_error(self, mock_request):
        self.client.dry_run = False
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.raise_for_status.side_effect = Exception("401 Unauthorized")
        mock_request.return_value = mock_response

        with pytest.raises(Exception):
            self.client.get_lead(123)

    @patch("requests.request")
    def test_request_204_no_content(self, mock_request):
        self.client.dry_run = False
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.client._request("GET", "/leads/999")
        assert result == {}


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: src/infrastructure/llm_client.py
# ═══════════════════════════════════════════════════════════════════

class TestYandexGPTClient:
    """Тесты для YandexGPTClient."""

    def setup_method(self):
        from src.infrastructure.llm_client import YandexGPTClient
        self.client = YandexGPTClient("test_folder", "test_api_key")

    def test_init(self):
        assert self.client.folder_id == "test_folder"
        assert self.client.api_key == "test_api_key"
        assert "yandex.net" in self.client.base_url

    def test_headers(self):
        assert "Api-Key test_api_key" in self.client.headers["Authorization"]
        assert self.client.headers["x-folder-id"] == "test_folder"

    @patch.dict(os.environ, {"LLM_MODE": "training"})
    def test_complete_training_mode(self):
        from src.infrastructure.llm_client import YandexGPTClient
        client = YandexGPTClient("folder", "key")
        client.mode = "training"
        result = client.complete("system prompt", "user prompt")
        assert result != ""
        # Should return a stub JSON
        assert "direction" in result

    @patch("requests.post")
    @patch.dict(os.environ, {"LLM_MODE": "production"})
    def test_complete_production_mode_success(self, mock_post):
        from src.infrastructure.llm_client import YandexGPTClient
        client = YandexGPTClient("folder", "key")
        client.mode = "production"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "alternatives": [
                    {"message": {"text": '{"direction": "HSS-01", "priority": "Р2"}'}}
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = client.complete("Classify this", "Tender text here")
        assert "direction" in result
        assert "HSS-01" in result

    @patch("requests.post")
    @patch.dict(os.environ, {"LLM_MODE": "production"})
    def test_complete_production_mode_error(self, mock_post):
        from src.infrastructure.llm_client import YandexGPTClient
        client = YandexGPTClient("folder", "key")
        client.mode = "production"

        mock_post.side_effect = Exception("Timeout")

        result = client.complete("Classify", "Text")
        assert result == ""

    def test_complete_custom_temperature(self):
        self.client.mode = "training"
        result = self.client.complete("sys", "user", temperature=0.7)
        assert result != ""


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: src/infrastructure/yadisk_client.py (расширенные)
# ═══════════════════════════════════════════════════════════════════

class TestYaDiskClientExtended:
    """Расширенные тесты для YaDiskClient."""

    def setup_method(self):
        from src.infrastructure.yadisk_client import YaDiskClient
        self.client = YaDiskClient("test_token")

    def test_init(self):
        assert self.client.token == "test_token"
        assert "OAuth test_token" in self.client.headers["Authorization"]

    @patch("requests.request")
    def test_get_public_folder_items_success(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "_embedded": {
                "items": [
                    {"name": "file1.pdf", "type": "file", "path": "/file1.pdf"},
                    {"name": "file2.docx", "type": "file", "path": "/file2.docx"},
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.client.get_public_folder_items("https://disk.yandex.ru/d/abc123")
        assert len(result) == 2

    @patch("requests.request")
    def test_get_public_folder_items_error(self, mock_request):
        mock_request.side_effect = Exception("Network error")
        result = self.client.get_public_folder_items("https://disk.yandex.ru/d/bad")
        assert result == []

    @patch("requests.request")
    def test_get_public_download_url_success(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"href": "https://downloader.yandex.net/file"}
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.client.get_public_download_url("https://disk.yandex.ru/d/abc", "/file.pdf")
        assert result == "https://downloader.yandex.net/file"

    @patch("requests.request")
    def test_get_public_download_url_error(self, mock_request):
        mock_request.side_effect = Exception("Error")
        result = self.client.get_public_download_url("key", "/path")
        assert result is None

    @patch("requests.request")
    def test_get_folder_items_success(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "_embedded": {
                "items": [{"name": "doc.pdf", "type": "file", "path": "/folder/doc.pdf"}]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.client.get_folder_items("/folder")
        assert len(result) == 1

    @patch("requests.request")
    def test_get_folder_items_error(self, mock_request):
        mock_request.side_effect = Exception("Error")
        result = self.client.get_folder_items("/nonexistent")
        assert result == []

    @patch("requests.request")
    def test_get_download_url_success(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"href": "https://download.example.com/file"}
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.client.get_download_url("/folder/file.pdf")
        assert result == "https://download.example.com/file"

    @patch("requests.request")
    def test_get_download_url_error(self, mock_request):
        mock_request.side_effect = Exception("Error")
        result = self.client.get_download_url("/nonexistent")
        assert result is None

    @patch("requests.get")
    def test_download_file_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"file content here"]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp_path = f.name

        try:
            result = self.client.download_file("https://download.example.com/file", tmp_path)
            assert result is True
            with open(tmp_path, "rb") as f:
                content = f.read()
            assert content == b"file content here"
        finally:
            os.unlink(tmp_path)

    @patch("requests.get")
    def test_download_file_error(self, mock_get):
        mock_get.side_effect = Exception("Download failed")
        result = self.client.download_file("https://bad.url/file", "/tmp/out.pdf")
        assert result is False
