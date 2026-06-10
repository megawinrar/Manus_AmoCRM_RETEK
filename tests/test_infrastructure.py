"""
Tests for infrastructure layer.
"""
import pytest
from unittest.mock import patch, MagicMock
from src.infrastructure.amocrm_client import AmoClient
from src.infrastructure.yadisk_client import YaDiskClient


class TestAmoClient:
    def setup_method(self):
        self.client = AmoClient("tokutools", "test_token")
        self.client.dry_run = True

    def test_dry_run_create_lead(self):
        result = self.client.create_lead("Test", 1, 1)
        assert result == 9999999

    def test_dry_run_update_lead(self):
        result = self.client.update_lead(123, status_id=456)
        assert result is True

    def test_dry_run_add_note(self):
        result = self.client.add_note(123, "Test note")
        assert result == 9999999

    def test_dry_run_add_task(self):
        result = self.client.add_task(123, "Test task", 1700000000)
        assert result == 9999999

    def test_headers_set(self):
        assert "Bearer test_token" in self.client.headers["Authorization"]

    def test_base_url(self):
        assert self.client.base_url == "https://tokutools.amocrm.ru/api/v4"


class TestYaDiskClient:
    def setup_method(self):
        self.client = YaDiskClient("test_token")

    def test_headers_set(self):
        assert "OAuth test_token" in self.client.headers["Authorization"]

    def test_base_url(self):
        assert self.client.base_url == "https://cloud-api.yandex.net/v1/disk"

    @patch("requests.get")
    def test_download_file(self, mock_get):
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"test data"]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        import tempfile, os
        tmp = tempfile.mktemp()
        result = self.client.download_file("http://example.com/file.pdf", tmp)
        assert result is True
        os.unlink(tmp)
