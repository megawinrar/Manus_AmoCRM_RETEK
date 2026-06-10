"""
Тесты для модуля action3_handler.py (src/microservice/action3_handler.py).

Покрытие:
- extract_yadisk_link — извлечение ссылки на Я.Диск
- download_from_public_link — скачивание файлов по публичной ссылке
- process_action3 — полный flow обработки действия 3
- Константы и regex

Запуск:
    pytest tests/test_action3_handler.py -v
"""

import os
import sys
import json
import pytest
import tempfile
from unittest.mock import patch, MagicMock

# Устанавливаем переменные окружения ДО импорта модулей
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
os.environ.setdefault("FIELD_CUSTOMER", "380299")
os.environ.setdefault("FIELD_NMC", "380315")
os.environ.setdefault("FIELD_DIRECTION", "380311")
os.environ.setdefault("FIELD_PRIORITY", "380309")
os.environ.setdefault("FIELD_PROCEDURE_NUM", "380303")
os.environ.setdefault("FIELD_SITUATION_TYPE", "380305")
os.environ.setdefault("FIELD_DEADLINE", "380317")
os.environ.setdefault("FIELD_LLM_CONFIDENCE", "380349")
os.environ.setdefault("FIELD_LLM_COMMENT", "380351")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.microservice.action3_handler import (
    extract_yadisk_link,
    download_from_public_link,
    process_action3,
    YADISK_PUBLIC_LINK_RE,
    YADISK_PATH_RE,
    SUPPORTED_EXTENSIONS,
    ENUM_PRIORITY,
    ENUM_DIRECTION,
    ENUM_SITUATION,
)


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ extract_yadisk_link
# ═══════════════════════════════════════════════════════════════════

class TestExtractYadiskLink:
    """Тесты извлечения ссылки на Я.Диск."""

    def test_public_link_disk_yandex_ru(self):
        text = "Вот ссылка: https://disk.yandex.ru/d/abc123def456 — скачайте"
        result = extract_yadisk_link(text)
        assert result == "https://disk.yandex.ru/d/abc123def456"

    def test_public_link_yadi_sk(self):
        text = "Файлы тут: https://yadi.sk/d/xyz789_test"
        result = extract_yadisk_link(text)
        assert result == "https://yadi.sk/d/xyz789_test"

    def test_internal_path(self):
        text = "Путь к файлам:\ndisk:/ТОРГИ/2025/06/Gesac - 86 поз.\n"
        result = extract_yadisk_link(text)
        assert result is not None
        assert "/ТОРГИ/" in result

    def test_internal_path_without_disk_prefix(self):
        text = "Файлы в папке:\n/ТОРГИ/2025/06/Тест\n"
        result = extract_yadisk_link(text)
        assert result is not None
        assert "/ТОРГИ/" in result

    def test_no_link_found(self):
        text = "Обычный текст без ссылок на диск"
        result = extract_yadisk_link(text)
        assert result is None

    def test_empty_text(self):
        result = extract_yadisk_link("")
        assert result is None

    def test_multiple_links_returns_first_public(self):
        text = "Ссылка 1: https://disk.yandex.ru/d/first123 и https://yadi.sk/d/second456"
        result = extract_yadisk_link(text)
        assert result == "https://disk.yandex.ru/d/first123"

    def test_public_link_preferred_over_path(self):
        text = "https://disk.yandex.ru/d/public123\ndisk:/ТОРГИ/2025/path"
        result = extract_yadisk_link(text)
        assert "disk.yandex.ru" in result

    def test_link_with_hyphen_underscore(self):
        text = "https://disk.yandex.ru/d/abc-def_123-xyz"
        result = extract_yadisk_link(text)
        assert result == "https://disk.yandex.ru/d/abc-def_123-xyz"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ download_from_public_link
# ═══════════════════════════════════════════════════════════════════

class TestDownloadFromPublicLink:
    """Тесты скачивания файлов по публичной ссылке."""

    @patch("src.microservice.action3_handler.requests.get")
    def test_download_success(self, mock_get):
        list_resp = MagicMock()
        list_resp.status_code = 200
        list_resp.json.return_value = {
            "_embedded": {
                "items": [
                    {"name": "spec.xlsx", "type": "file", "path": "/spec.xlsx", "size": 1024},
                    {"name": "tz.pdf", "type": "file", "path": "/tz.pdf", "size": 2048},
                ]
            }
        }
        dl_resp = MagicMock()
        dl_resp.status_code = 200
        dl_resp.json.return_value = {"href": "https://downloader.disk.yandex.ru/file"}
        file_resp = MagicMock()
        file_resp.iter_content.return_value = [b"file content"]

        mock_get.side_effect = [list_resp, dl_resp, file_resp, dl_resp, file_resp]

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_from_public_link("https://disk.yandex.ru/d/test123", tmp_dir)
        assert len(result) == 2

    @patch("src.microservice.action3_handler.requests.get")
    def test_download_api_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_from_public_link("https://disk.yandex.ru/d/bad", tmp_dir)
        assert result == []

    @patch("src.microservice.action3_handler.requests.get")
    def test_download_skips_hidden_files(self, mock_get):
        list_resp = MagicMock()
        list_resp.status_code = 200
        list_resp.json.return_value = {
            "_embedded": {
                "items": [
                    {"name": "._hidden.pdf", "type": "file", "path": "/._hidden.pdf", "size": 100},
                    {"name": "~$temp.docx", "type": "file", "path": "/~$temp.docx", "size": 200},
                    {"name": "real.xlsx", "type": "file", "path": "/real.xlsx", "size": 1024},
                ]
            }
        }
        dl_resp = MagicMock()
        dl_resp.status_code = 200
        dl_resp.json.return_value = {"href": "https://downloader.disk.yandex.ru/f"}
        file_resp = MagicMock()
        file_resp.iter_content.return_value = [b"data"]

        mock_get.side_effect = [list_resp, dl_resp, file_resp]

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_from_public_link("https://disk.yandex.ru/d/test", tmp_dir)
        assert len(result) == 1

    @patch("src.microservice.action3_handler.requests.get")
    def test_download_empty_folder(self, mock_get):
        list_resp = MagicMock()
        list_resp.status_code = 200
        list_resp.json.return_value = {"_embedded": {"items": []}}
        mock_get.return_value = list_resp

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_from_public_link("https://disk.yandex.ru/d/empty", tmp_dir)
        assert result == []

    @patch("src.microservice.action3_handler.requests.get")
    def test_download_filters_unsupported_extensions(self, mock_get):
        list_resp = MagicMock()
        list_resp.status_code = 200
        list_resp.json.return_value = {
            "_embedded": {
                "items": [
                    {"name": "video.mp4", "type": "file", "path": "/video.mp4", "size": 5000},
                    {"name": "spec.pdf", "type": "file", "path": "/spec.pdf", "size": 1024},
                ]
            }
        }
        dl_resp = MagicMock()
        dl_resp.status_code = 200
        dl_resp.json.return_value = {"href": "https://downloader.disk.yandex.ru/f"}
        file_resp = MagicMock()
        file_resp.iter_content.return_value = [b"data"]
        mock_get.side_effect = [list_resp, dl_resp, file_resp]

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_from_public_link("https://disk.yandex.ru/d/test", tmp_dir)
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ process_action3
# ═══════════════════════════════════════════════════════════════════

class TestProcessAction3:
    """Тесты полного flow process_action3."""

    @patch("src.microservice.action3_handler.AmoClient")
    @patch("src.microservice.action3_handler.download_from_public_link")
    @patch("src.microservice.action3_handler.run_extraction_and_classification")
    def test_full_flow_success(self, mock_classify, mock_download, mock_client_cls):
        mock_download.return_value = ["/tmp/spec.xlsx"]
        mock_classify.return_value = {
            "customer": "ООО Тест",
            "nmc": "500000",
            "direction": "CARBIDE-STANDARD",
            "priority": "P2",
            "deadline": "2025-08-01",
            "procedure_number": "12345",
            "situation_type": "Запрос котировок / реальные торги",
            "confidence": {"overall": 0.9},
            "validation_status": "valid",
        }
        mock_client = MagicMock()
        mock_client.update_lead.return_value = True
        mock_client.add_note.return_value = True
        mock_client.create_task.return_value = True
        mock_client_cls.return_value = mock_client

        note_text = "Файлы: https://disk.yandex.ru/d/abc123"
        result = process_action3(lead_id=123, note_text=note_text)

        assert result is True
        mock_client.update_lead.assert_called_once()
        mock_client.create_task.assert_called_once()

    def test_no_link_in_text(self):
        result = process_action3(lead_id=123, note_text="Текст без ссылки")
        assert result is False

    @patch("src.microservice.action3_handler.AmoClient")
    @patch("src.microservice.action3_handler.download_from_public_link")
    def test_download_returns_empty(self, mock_download, mock_client_cls):
        mock_download.return_value = []
        mock_client = MagicMock()
        mock_client.add_note.return_value = True
        mock_client_cls.return_value = mock_client

        note_text = "https://disk.yandex.ru/d/broken_link"
        result = process_action3(lead_id=123, note_text=note_text)
        assert result is True
        mock_client.add_note.assert_called()

    @patch("src.microservice.action3_handler.AmoClient")
    @patch("src.microservice.action3_handler.download_from_public_link")
    @patch("src.microservice.action3_handler.run_extraction_and_classification")
    def test_classification_error(self, mock_classify, mock_download, mock_client_cls):
        mock_download.return_value = ["/tmp/file.pdf"]
        mock_classify.return_value = {"error": "OCR failed"}
        mock_client = MagicMock()
        mock_client.add_note.return_value = True
        mock_client_cls.return_value = mock_client

        note_text = "https://disk.yandex.ru/d/test123"
        result = process_action3(lead_id=123, note_text=note_text)
        assert result is True

    @patch("src.microservice.action3_handler.AmoClient")
    @patch("src.microservice.action3_handler.download_from_public_link")
    def test_exception_handling(self, mock_download, mock_client_cls):
        mock_download.side_effect = Exception("Unexpected error")
        mock_client = MagicMock()
        mock_client.add_note.return_value = True
        mock_client_cls.return_value = mock_client

        note_text = "https://disk.yandex.ru/d/test123"
        result = process_action3(lead_id=123, note_text=note_text)
        assert result is True

    @patch("src.microservice.action3_handler.AmoClient")
    @patch("src.microservice.action3_handler.download_from_public_link")
    @patch("src.microservice.action3_handler.run_extraction_and_classification")
    def test_nmc_string_conversion(self, mock_classify, mock_download, mock_client_cls):
        """NMC строка конвертируется в число."""
        mock_download.return_value = ["/tmp/spec.xlsx"]
        mock_classify.return_value = {
            "customer": "Тест",
            "nmc": "1 500 000,50",
            "direction": "HSS-STANDARD",
            "priority": "P3",
            "deadline": "",
            "procedure_number": "",
            "situation_type": "Запрос котировок / реальные торги",
            "confidence": 0.8,
            "validation_status": "valid",
        }
        mock_client = MagicMock()
        mock_client.update_lead.return_value = True
        mock_client.add_note.return_value = True
        mock_client.create_task.return_value = True
        mock_client_cls.return_value = mock_client

        note_text = "https://disk.yandex.ru/d/test"
        result = process_action3(lead_id=456, note_text=note_text)
        assert result is True


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ КОНСТАНТ
# ═══════════════════════════════════════════════════════════════════

class TestConstants:
    """Тесты констант и regex."""

    def test_supported_extensions(self):
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".xlsx" in SUPPORTED_EXTENSIONS
        assert ".docx" in SUPPORTED_EXTENSIONS
        assert ".doc" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS

    def test_enum_priority(self):
        assert "P1" in ENUM_PRIORITY or "Р1" in ENUM_PRIORITY
        assert "P4" in ENUM_PRIORITY or "Р4" in ENUM_PRIORITY

    def test_enum_situation(self):
        assert "СОЗ" in ENUM_SITUATION
        assert "Запрос котировок / реальные торги" in ENUM_SITUATION

    def test_yadisk_public_link_regex(self):
        assert YADISK_PUBLIC_LINK_RE.search("https://disk.yandex.ru/d/abc123")
        assert YADISK_PUBLIC_LINK_RE.search("https://yadi.sk/d/xyz789")
        assert not YADISK_PUBLIC_LINK_RE.search("https://google.com/file")

    def test_yadisk_path_regex(self):
        assert YADISK_PATH_RE.search("/ТОРГИ/2025/06/Тест")
        assert YADISK_PATH_RE.search("disk:/ТОРГИ/2025/06/Тест")
