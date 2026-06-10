"""
Тесты для cron_yadisk — сканирование Яндекс.Диска и обработка тендеров.

Покрытие:
- init_db — инициализация SQLite
- is_tender_processed — проверка обработанных тендеров
- mark_tender_processed — запись тендера
- update_tender_status — обновление статуса
- YaDiskClient.list_folder — получение списка файлов
- YaDiskClient.get_download_url — получение URL скачивания
- YaDiskClient.download_file — скачивание файла
- scan_root_folder — сканирование корневой папки
- collect_files_recursive — рекурсивный сбор файлов
- extract_archives — распаковка ZIP
- _extract_customer_from_folder_name — извлечение заказчика
- run_yadisk_scan — основная функция

Запуск:
    pytest tests/test_cron_yadisk.py -v
"""
import os
import sys
import json
import sqlite3
import tempfile
import zipfile
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime

# Устанавливаем переменные окружения ДО импорта
os.environ.setdefault("AMO_DOMAIN", "tokutools.amocrm.ru")
os.environ.setdefault("AMO_ACCESS_TOKEN", "test_token")
os.environ.setdefault("YADISK_TOKEN", "test_yadisk_token")
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

from src.microservice.cron_yadisk import (
    init_db,
    is_tender_processed,
    mark_tender_processed,
    update_tender_status,
    YaDiskClient,
    scan_root_folder,
    collect_files_recursive,
    extract_archives,
    _extract_customer_from_folder_name,
    run_yadisk_scan,
)


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    with patch("src.microservice.cron_yadisk.DB_PATH", db_path):
        conn = init_db()
        yield conn, db_path
    conn.close()
    os.unlink(db_path)


@pytest.fixture
def mock_yadisk_client():
    """Create a YaDiskClient with mocked session."""
    with patch("src.microservice.cron_yadisk.YADISK_TOKEN", "test_token"):
        client = YaDiskClient(token="test_token")
        client.session = MagicMock()
    return client


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: init_db
# ═══════════════════════════════════════════════════════════════════

class TestInitDb:
    def test_creates_tables(self, temp_db):
        conn, _ = temp_db
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        assert "processed_tenders" in tables
        assert "processed_files" in tables

    def test_idempotent_creation(self, temp_db):
        conn, db_path = temp_db
        # Call init_db again — should not fail
        with patch("src.microservice.cron_yadisk.DB_PATH", db_path):
            conn2 = init_db()
            cursor = conn2.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            assert "processed_tenders" in tables
            conn2.close()


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: is_tender_processed / mark_tender_processed
# ═══════════════════════════════════════════════════════════════════

class TestTenderProcessing:
    def test_new_tender_not_processed(self, temp_db):
        conn, _ = temp_db
        assert is_tender_processed(conn, "/ТОРГИ/09.06/Gesac") is False

    def test_mark_and_check_processed(self, temp_db):
        conn, _ = temp_db
        mark_tender_processed(
            conn,
            folder_path="/ТОРГИ/09.06/Gesac",
            folder_name="Gesac",
            date_folder="09.06",
            file_count=3,
            total_size=1024000,
            status="done",
        )
        assert is_tender_processed(conn, "/ТОРГИ/09.06/Gesac") is True

    def test_pending_status_not_considered_processed(self, temp_db):
        conn, _ = temp_db
        mark_tender_processed(
            conn,
            folder_path="/ТОРГИ/09.06/Pending",
            folder_name="Pending",
            date_folder="09.06",
            file_count=1,
            total_size=500,
            status="pending",
        )
        assert is_tender_processed(conn, "/ТОРГИ/09.06/Pending") is False

    def test_error_status_not_considered_processed(self, temp_db):
        conn, _ = temp_db
        mark_tender_processed(
            conn,
            folder_path="/ТОРГИ/09.06/Error",
            folder_name="Error",
            date_folder="09.06",
            file_count=1,
            total_size=500,
            status="error",
        )
        assert is_tender_processed(conn, "/ТОРГИ/09.06/Error") is False

    def test_update_tender_status(self, temp_db):
        conn, _ = temp_db
        mark_tender_processed(
            conn,
            folder_path="/ТОРГИ/09.06/Update",
            folder_name="Update",
            date_folder="09.06",
            file_count=2,
            total_size=2048,
            status="pending",
        )
        update_tender_status(
            conn,
            folder_path="/ТОРГИ/09.06/Update",
            status="done",
            amo_lead_id=12345,
            llm_result='{"priority": "Р1"}',
        )
        cursor = conn.execute(
            "SELECT status, amo_lead_id FROM processed_tenders WHERE folder_path = ?",
            ("/ТОРГИ/09.06/Update",)
        )
        row = cursor.fetchone()
        assert row[0] == "done"
        assert row[1] == 12345


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: YaDiskClient
# ═══════════════════════════════════════════════════════════════════

class TestYaDiskClientCron:
    def test_init(self, mock_yadisk_client):
        assert mock_yadisk_client.token == "test_token"

    def test_list_folder_success(self, mock_yadisk_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "_embedded": {
                "items": [
                    {"name": "file1.pdf", "type": "file", "path": "disk:/ТОРГИ/file1.pdf",
                     "size": 1024, "mime_type": "application/pdf", "modified": "2025-06-01"},
                    {"name": "subfolder", "type": "dir", "path": "disk:/ТОРГИ/subfolder",
                     "size": 0, "mime_type": "", "modified": "2025-06-01"},
                ]
            }
        }
        mock_yadisk_client.session.get.return_value = mock_resp
        items = mock_yadisk_client.list_folder("/ТОРГИ")
        assert len(items) == 2
        assert items[0]["name"] == "file1.pdf"
        assert items[0]["type"] == "file"
        assert items[1]["type"] == "dir"

    def test_list_folder_not_found(self, mock_yadisk_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_yadisk_client.session.get.return_value = mock_resp
        items = mock_yadisk_client.list_folder("/nonexistent")
        assert items == []

    def test_get_download_url_success(self, mock_yadisk_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"href": "https://downloader.disk.yandex.net/file123"}
        mock_yadisk_client.session.get.return_value = mock_resp
        url = mock_yadisk_client.get_download_url("/ТОРГИ/file1.pdf")
        assert url == "https://downloader.disk.yandex.net/file123"

    def test_get_download_url_failure(self, mock_yadisk_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_yadisk_client.session.get.return_value = mock_resp
        url = mock_yadisk_client.get_download_url("/nonexistent")
        assert url is None

    @patch("requests.get")
    def test_download_file_success(self, mock_requests_get, mock_yadisk_client):
        # Mock get_download_url
        mock_resp_url = MagicMock()
        mock_resp_url.status_code = 200
        mock_resp_url.json.return_value = {"href": "https://download.example.com/file"}
        mock_yadisk_client.session.get.return_value = mock_resp_url

        # Mock actual download
        mock_download_resp = MagicMock()
        mock_download_resp.status_code = 200
        mock_download_resp.iter_content.return_value = [b"test data content"]
        mock_requests_get.return_value = mock_download_resp

        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp_path = f.name

        try:
            result = mock_yadisk_client.download_file("/ТОРГИ/file.pdf", tmp_path)
            assert result is True
            with open(tmp_path, "rb") as f:
                assert f.read() == b"test data content"
        finally:
            os.unlink(tmp_path)

    def test_download_file_no_url(self, mock_yadisk_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_yadisk_client.session.get.return_value = mock_resp
        result = mock_yadisk_client.download_file("/nonexistent", "/tmp/out.pdf")
        assert result is False


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: scan_root_folder / collect_files_recursive
# ═══════════════════════════════════════════════════════════════════

class TestScanFunctions:
    def test_scan_root_folder_empty(self):
        mock_client = MagicMock()
        mock_client.list_folder.return_value = []
        result = scan_root_folder(mock_client)
        assert result == []

    def test_scan_root_folder_with_date_folders(self):
        mock_client = MagicMock()
        # Root level: date folders
        mock_client.list_folder.side_effect = [
            # Root folder
            [
                {"name": "09.06.2025", "type": "dir", "path": "/ТОРГИ/09.06.2025"},
                {"name": "10.06.2025", "type": "dir", "path": "/ТОРГИ/10.06.2025"},
                {"name": "README.txt", "type": "file", "path": "/ТОРГИ/README.txt"},
            ],
            # Date folder 1: tender folders
            [
                {"name": "Gesac", "type": "dir", "path": "/ТОРГИ/09.06.2025/Gesac"},
            ],
            # Tender folder files
            [
                {"name": "ТЗ.pdf", "type": "file", "path": "/ТОРГИ/09.06.2025/Gesac/ТЗ.pdf",
                 "size": 5000, "mime_type": "application/pdf", "modified": "2025-06-09"},
            ],
            # Date folder 2: empty
            [],
        ]
        result = scan_root_folder(mock_client)
        assert len(result) == 1
        assert result[0]["folder_name"] == "Gesac"
        assert result[0]["date_folder"] == "09.06.2025"
        assert len(result[0]["files"]) == 1

    def test_collect_files_recursive_flat(self):
        mock_client = MagicMock()
        mock_client.list_folder.return_value = [
            {"name": "doc.pdf", "type": "file", "path": "/folder/doc.pdf",
             "size": 1024, "mime_type": "application/pdf", "modified": "2025-06-01"},
            {"name": "spec.docx", "type": "file", "path": "/folder/spec.docx",
             "size": 2048, "mime_type": "application/docx", "modified": "2025-06-01"},
        ]
        result = collect_files_recursive(mock_client, "/folder")
        assert len(result) == 2

    def test_collect_files_recursive_skips_hidden(self):
        mock_client = MagicMock()
        mock_client.list_folder.return_value = [
            {"name": "._hidden.pdf", "type": "file", "path": "/folder/._hidden.pdf",
             "size": 100, "mime_type": "application/pdf", "modified": "2025-06-01"},
            {"name": "~$temp.docx", "type": "file", "path": "/folder/~$temp.docx",
             "size": 200, "mime_type": "application/docx", "modified": "2025-06-01"},
            {"name": "real.pdf", "type": "file", "path": "/folder/real.pdf",
             "size": 1024, "mime_type": "application/pdf", "modified": "2025-06-01"},
        ]
        result = collect_files_recursive(mock_client, "/folder")
        assert len(result) == 1
        assert result[0]["name"] == "real.pdf"

    def test_collect_files_recursive_with_subdirectory(self):
        mock_client = MagicMock()
        mock_client.list_folder.side_effect = [
            # Parent folder
            [
                {"name": "main.pdf", "type": "file", "path": "/folder/main.pdf",
                 "size": 1024, "mime_type": "application/pdf", "modified": "2025-06-01"},
                {"name": "sub", "type": "dir", "path": "/folder/sub"},
            ],
            # Subfolder
            [
                {"name": "sub_file.xlsx", "type": "file", "path": "/folder/sub/sub_file.xlsx",
                 "size": 2048, "mime_type": "application/xlsx", "modified": "2025-06-01"},
            ],
        ]
        result = collect_files_recursive(mock_client, "/folder")
        assert len(result) == 2

    def test_collect_files_max_depth(self):
        mock_client = MagicMock()
        mock_client.list_folder.return_value = [
            {"name": "deep", "type": "dir", "path": "/a/b/c/deep"},
        ]
        # At max depth, should return empty
        result = collect_files_recursive(mock_client, "/a/b/c/deep", depth=10)
        assert result == []


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: extract_archives
# ═══════════════════════════════════════════════════════════════════

class TestExtractArchives:
    def test_no_archives(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a regular file
            pdf_path = os.path.join(tmp_dir, "doc.pdf")
            with open(pdf_path, "w") as f:
                f.write("PDF content")
            result = extract_archives([pdf_path], tmp_dir)
            assert result == [pdf_path]

    def test_extract_valid_zip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a zip file with a PDF inside
            zip_path = os.path.join(tmp_dir, "archive.zip")
            pdf_content = b"Fake PDF content"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("document.pdf", pdf_content)

            result = extract_archives([zip_path], tmp_dir)
            assert len(result) >= 1
            # The extracted file should exist
            extracted_names = [os.path.basename(f) for f in result]
            assert "document.pdf" in extracted_names

    def test_extract_zip_skips_macosx(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = os.path.join(tmp_dir, "archive.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("__MACOSX/._hidden", "hidden data")
                zf.writestr("real_doc.pdf", "Real content")

            result = extract_archives([zip_path], tmp_dir)
            extracted_names = [os.path.basename(f) for f in result]
            assert "real_doc.pdf" in extracted_names
            assert "._hidden" not in extracted_names

    def test_extract_bad_zip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_zip_path = os.path.join(tmp_dir, "bad.zip")
            with open(bad_zip_path, "w") as f:
                f.write("This is not a zip file")

            result = extract_archives([bad_zip_path], tmp_dir)
            # Bad zip should be kept as-is (fallback)
            assert bad_zip_path in result


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: _extract_customer_from_folder_name
# ═══════════════════════════════════════════════════════════════════

class TestExtractCustomer:
    def test_simple_customer(self):
        result = _extract_customer_from_folder_name("АО НПП ИСТОК ШОКИНА - Не интересно - Калибры")
        assert result == "АО НПП ИСТОК ШОКИНА"

    def test_customer_with_positions(self):
        result = _extract_customer_from_folder_name("Gesac - 86 поз.")
        assert result == "Gesac"

    def test_customer_with_amount(self):
        result = _extract_customer_from_folder_name("АО ОКБ ФАКЕЛ - твердосплав 350к руб")
        assert result == "АО ОКБ ФАКЕЛ"

    def test_single_name_no_separator(self):
        result = _extract_customer_from_folder_name("SimpleCustomer")
        assert result == "SimpleCustomer"

    def test_empty_string(self):
        result = _extract_customer_from_folder_name("")
        assert result == ""


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ: run_yadisk_scan
# ═══════════════════════════════════════════════════════════════════

class TestRunYadiskScan:
    @patch("src.microservice.cron_yadisk.YADISK_TOKEN", "")
    def test_no_token_returns_error(self):
        result = run_yadisk_scan(dry_run=True)
        assert "error" in result

    @patch("src.microservice.cron_yadisk.scan_root_folder")
    @patch("src.microservice.cron_yadisk.init_db")
    @patch("src.microservice.cron_yadisk.YaDiskClient")
    @patch("src.microservice.cron_yadisk.YADISK_TOKEN", "test_token")
    def test_empty_scan(self, mock_client_cls, mock_init_db, mock_scan):
        mock_scan.return_value = []
        mock_conn = MagicMock()
        mock_init_db.return_value = mock_conn

        # Mock deduplication imports
        with patch.dict("sys.modules", {
            "src.microservice.deduplication": MagicMock()
        }):
            result = run_yadisk_scan(dry_run=True)
            assert isinstance(result, dict)
            assert result.get("total_scanned", 0) == 0

    @patch("src.microservice.cron_yadisk.scan_root_folder")
    @patch("src.microservice.cron_yadisk.init_db")
    @patch("src.microservice.cron_yadisk.YaDiskClient")
    @patch("src.microservice.cron_yadisk.YADISK_TOKEN", "test_token")
    def test_scan_with_already_processed_tender(self, mock_client_cls, mock_init_db, mock_scan):
        mock_scan.return_value = [
            {
                "folder_path": "/ТОРГИ/09.06/Gesac",
                "folder_name": "Gesac",
                "date_folder": "09.06",
                "files": [{"name": "doc.pdf", "path": "/ТОРГИ/09.06/Gesac/doc.pdf", "size": 1024}],
            }
        ]
        mock_conn = MagicMock()
        mock_init_db.return_value = mock_conn

        with patch.dict("sys.modules", {
            "src.microservice.deduplication": MagicMock()
        }):
            with patch("src.microservice.cron_yadisk.is_tender_processed", return_value=True):
                result = run_yadisk_scan(dry_run=True)
                assert isinstance(result, dict)
