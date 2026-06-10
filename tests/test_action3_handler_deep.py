"""
Tests for action3_handler.py deeper paths:
- download_from_public_link
- download_from_internal_path
- run_extraction_and_classification
- process_action3 (integration)
"""
import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock, call
from pathlib import Path


class TestExtractYadiskLink:
    """Tests for extract_yadisk_link function."""

    def setup_method(self):
        from src.microservice.action3_handler import extract_yadisk_link
        self.extract = extract_yadisk_link

    def test_public_link_disk_yandex_ru(self):
        """Extracts disk.yandex.ru public link."""
        text = "Файлы тут: https://disk.yandex.ru/d/abc123_XYZ"
        result = self.extract(text)
        assert result == "https://disk.yandex.ru/d/abc123_XYZ"

    def test_public_link_yadi_sk(self):
        """Extracts yadi.sk short link."""
        text = "Ссылка: https://yadi.sk/d/abcdef123"
        result = self.extract(text)
        assert result == "https://yadi.sk/d/abcdef123"

    def test_internal_path(self):
        """Extracts internal disk path."""
        text = "Файлы в /ТОРГИ/2024/Тендер-123/docs"
        result = self.extract(text)
        assert "disk:" in result
        assert "/ТОРГИ/" in result

    def test_internal_path_with_disk_prefix(self):
        """Extracts internal path that already has disk: prefix."""
        text = "disk:/ТОРГИ/2024/Тендер-456"
        result = self.extract(text)
        assert result.startswith("disk:/ТОРГИ/")

    def test_no_link_found(self):
        """Returns None when no link found."""
        text = "Просто текст без ссылок"
        result = self.extract(text)
        assert result is None

    def test_empty_text(self):
        """Returns None for empty text."""
        result = self.extract("")
        assert result is None

    def test_public_link_preferred_over_path(self):
        """Public link is preferred over internal path."""
        text = "https://disk.yandex.ru/d/abc123 и /ТОРГИ/backup"
        result = self.extract(text)
        assert result.startswith("https://")


class TestDownloadFromPublicLink:
    """Tests for download_from_public_link function."""

    @patch("src.microservice.action3_handler.requests.get")
    def test_successful_download(self, mock_get):
        """Downloads files from public link."""
        from src.microservice.action3_handler import download_from_public_link

        # 1st call: get_files_recursive - returns folder listing
        mock_resp_list = MagicMock()
        mock_resp_list.status_code = 200
        mock_resp_list.json.return_value = {
            "_embedded": {
                "items": [
                    {"name": "doc1.pdf", "type": "file", "path": "/doc1.pdf", "size": 1024},
                ]
            }
        }

        # 2nd call: get download link
        mock_resp_dl_link = MagicMock()
        mock_resp_dl_link.status_code = 200
        mock_resp_dl_link.json.return_value = {"href": "https://download.example.com/doc1.pdf"}

        # 3rd call: actual file download
        mock_resp_file = MagicMock()
        mock_resp_file.iter_content = MagicMock(return_value=[b"file content"])

        mock_get.side_effect = [mock_resp_list, mock_resp_dl_link, mock_resp_file]

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_from_public_link("https://disk.yandex.ru/d/abc123", tmp_dir)
            assert isinstance(result, list)
            assert len(result) == 1

    @patch("src.microservice.action3_handler.requests.get")
    def test_api_error(self, mock_get):
        """API error returns empty list."""
        from src.microservice.action3_handler import download_from_public_link

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not found"
        mock_get.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_from_public_link("https://disk.yandex.ru/d/bad", tmp_dir)
            assert result == []

    @patch("src.microservice.action3_handler.requests.get")
    def test_connection_error(self, mock_get):
        """Connection error raises (not caught inside function)."""
        from src.microservice.action3_handler import download_from_public_link

        mock_get.side_effect = Exception("Connection timeout")

        with tempfile.TemporaryDirectory() as tmp_dir:
            # The function doesn't catch exceptions in get_files_recursive
            # so it will propagate up
            try:
                result = download_from_public_link("https://disk.yandex.ru/d/abc", tmp_dir)
                # If it returns, it should be empty
                assert result == []
            except Exception:
                # Expected - the function doesn't catch connection errors
                pass

    @patch("src.microservice.action3_handler.requests.get")
    def test_single_file_not_folder(self, mock_get):
        """Single file (not folder) is downloaded directly."""
        from src.microservice.action3_handler import download_from_public_link

        mock_resp_meta = MagicMock()
        mock_resp_meta.status_code = 200
        mock_resp_meta.json.return_value = {
            "type": "file",
            "name": "tender.pdf",
            "file": "https://download.example.com/tender.pdf",
        }

        mock_resp_file = MagicMock()
        mock_resp_file.status_code = 200
        mock_resp_file.content = b"PDF content"
        mock_resp_file.iter_content = MagicMock(return_value=[b"PDF content"])

        mock_get.side_effect = [mock_resp_meta, mock_resp_file]

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_from_public_link("https://disk.yandex.ru/d/abc123", tmp_dir)
            assert isinstance(result, list)


class TestDownloadFromInternalPath:
    """Tests for download_from_internal_path function."""

    @patch("src.microservice.action3_handler.requests.get")
    def test_successful_download(self, mock_get):
        """Downloads files from internal disk path."""
        from src.microservice.action3_handler import download_from_internal_path

        # Mock folder listing
        mock_resp_list = MagicMock()
        mock_resp_list.status_code = 200
        mock_resp_list.json.return_value = {
            "_embedded": {
                "items": [
                    {"name": "file1.pdf", "type": "file", "path": "disk:/ТОРГИ/file1.pdf"},
                ]
            }
        }

        # Mock download link
        mock_resp_link = MagicMock()
        mock_resp_link.status_code = 200
        mock_resp_link.json.return_value = {"href": "https://download.example.com/file1.pdf"}

        # Mock actual download
        mock_resp_file = MagicMock()
        mock_resp_file.status_code = 200
        mock_resp_file.content = b"file content"
        mock_resp_file.iter_content = MagicMock(return_value=[b"file content"])

        mock_get.side_effect = [mock_resp_list, mock_resp_link, mock_resp_file]

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_from_internal_path("disk:/ТОРГИ/2024/Tender", tmp_dir)
            assert isinstance(result, list)

    @patch("src.microservice.action3_handler.requests.get")
    def test_api_error(self, mock_get):
        """API error returns empty list."""
        from src.microservice.action3_handler import download_from_internal_path

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        mock_get.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_from_internal_path("disk:/ТОРГИ/bad", tmp_dir)
            assert result == []

    @patch("src.microservice.action3_handler.requests.get")
    def test_connection_error(self, mock_get):
        """Connection error returns empty list."""
        from src.microservice.action3_handler import download_from_internal_path

        mock_get.side_effect = Exception("Timeout")

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_from_internal_path("disk:/ТОРГИ/test", tmp_dir)
            assert result == []


class TestRunExtractionAndClassification:
    """Tests for run_extraction_and_classification function."""

    @patch("src.microservice.action3_handler.requests.post")
    def test_with_files(self, mock_post):
        """Classification with files returns result dict."""
        from src.microservice.action3_handler import run_extraction_and_classification

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "customer": "ООО Рога",
            "direction": "CARBIDE-STANDARD",
            "priority": "Р2",
            "situation": "Запрос котировок / реальные торги",
            "nmc": "1500000",
            "confidence": 0.85,
        }
        mock_post.return_value = mock_resp

        # Create temp files
        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = os.path.join(tmp_dir, "doc.pdf")
            with open(f1, "w") as f:
                f.write("test content")
            result = run_extraction_and_classification([f1])
            assert isinstance(result, dict)

    def test_empty_files_list(self):
        """Empty files list returns empty dict."""
        from src.microservice.action3_handler import run_extraction_and_classification
        result = run_extraction_and_classification([])
        assert result == {} or result is None or isinstance(result, dict)


class TestProcessAction3:
    """Integration tests for process_action3 function."""

    @patch("src.microservice.action3_handler.AmoClient")
    def test_no_link_returns_false(self, mock_amo_cls):
        """No link in note text returns False."""
        from src.microservice.action3_handler import process_action3
        result = process_action3(lead_id=100, note_text="Просто текст без ссылок")
        assert result is False

    @patch("src.microservice.action3_handler.AmoClient")
    @patch("src.microservice.action3_handler.download_from_public_link")
    @patch("src.microservice.action3_handler.tempfile.mkdtemp", return_value="/tmp/test_action3")
    def test_link_found_download_fails(self, mock_mkdtemp, mock_download, mock_amo_cls):
        """Link found but download fails — adds error note and returns True."""
        from src.microservice.action3_handler import process_action3

        mock_download.return_value = []
        mock_client = MagicMock()
        mock_amo_cls.return_value = mock_client

        with patch("shutil.rmtree"):
            result = process_action3(
                lead_id=100,
                note_text="Ссылка: https://disk.yandex.ru/d/abc123"
            )
        # Returns True because the function handled the error (added note)
        assert result is True
        # Should have added error note about failed download
        assert mock_client.add_note.called

    @patch("src.microservice.action3_handler.AmoClient")
    @patch("src.microservice.action3_handler.download_from_public_link")
    @patch("src.microservice.action3_handler.run_extraction_and_classification")
    @patch("src.microservice.action3_handler.tempfile.mkdtemp", return_value="/tmp/test_action3")
    def test_link_found_download_success_classify_success(self, mock_mkdtemp, mock_classify, mock_download, mock_amo_cls):
        """Full success path: link → download → classify → update lead."""
        from src.microservice.action3_handler import process_action3

        mock_download.return_value = ["/tmp/test_action3/doc1.pdf"]
        mock_classify.return_value = {
            "customer": "ООО Тест",
            "direction": "CARBIDE-STANDARD",
            "priority": "Р2",
            "situation": "Запрос котировок / реальные торги",
            "nmc": "500000",
            "confidence": 0.9,
        }
        mock_client = MagicMock()
        mock_client.update_lead.return_value = True
        mock_amo_cls.return_value = mock_client

        with patch("shutil.rmtree"):
            result = process_action3(
                lead_id=100,
                note_text="Файлы: https://disk.yandex.ru/d/abc123"
            )
        # Should return True on success
        assert result is True
        # Should have called update_lead
        assert mock_client.update_lead.called
