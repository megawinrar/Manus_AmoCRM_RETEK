"""
Deeper tests for cron_yadisk.py:
- mark_tender_processed (correct signature: conn, folder_path, folder_name, date_folder, file_count, total_size, ...)
- update_tender_status (correct signature: conn, folder_path, status, ...)
- _post_note_to_lead (lead_id, text)
- _update_lead_fields (lead_id, custom_fields)
- _extract_customer_from_folder_name (folder_name)
- run_yadisk_scan deeper paths
- format_enrichment_note from deduplication.py
"""
import pytest
import sqlite3
import os
import tempfile
from unittest.mock import patch, MagicMock
from dataclasses import dataclass, field
from datetime import datetime


@pytest.fixture
def db_conn():
    """Create a temporary SQLite database with the processed_tenders schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_tenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_path TEXT UNIQUE,
            folder_name TEXT,
            date_folder TEXT,
            file_count INTEGER,
            total_size INTEGER,
            processed_at TEXT,
            status TEXT DEFAULT 'pending',
            amo_lead_id INTEGER,
            llm_result TEXT,
            error TEXT
        )
    """)
    conn.commit()
    yield conn
    conn.close()
    os.unlink(db_path)


class TestPostNoteToLead:
    """Tests for _post_note_to_lead helper function."""

    @patch("src.microservice.cron_yadisk.requests.post")
    def test_successful_post(self, mock_post):
        """Successfully posts a note to lead."""
        from src.microservice.cron_yadisk import _post_note_to_lead

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        _post_note_to_lead(lead_id=100, text="Test note")
        assert mock_post.called

    @patch("src.microservice.cron_yadisk.requests.post")
    def test_api_error_logged(self, mock_post):
        """API error is logged but doesn't raise."""
        from src.microservice.cron_yadisk import _post_note_to_lead

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_post.return_value = mock_resp

        # Should not raise
        _post_note_to_lead(lead_id=100, text="Test note")

    @patch("src.microservice.cron_yadisk.requests.post")
    def test_connection_error_handled(self, mock_post):
        """Connection error is handled gracefully."""
        from src.microservice.cron_yadisk import _post_note_to_lead

        mock_post.side_effect = Exception("Connection timeout")

        # Should not raise
        _post_note_to_lead(lead_id=100, text="Test note")

    @patch("src.microservice.cron_yadisk.requests.post")
    def test_201_status_success(self, mock_post):
        """201 status is also considered success."""
        from src.microservice.cron_yadisk import _post_note_to_lead

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_post.return_value = mock_resp

        _post_note_to_lead(lead_id=100, text="Test note")
        assert mock_post.called


class TestUpdateLeadFields:
    """Tests for _update_lead_fields helper function."""

    @patch("src.microservice.cron_yadisk.requests.patch")
    def test_successful_update(self, mock_patch):
        """Successfully updates lead fields."""
        from src.microservice.cron_yadisk import _update_lead_fields

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_patch.return_value = mock_resp

        fields = [{"field_id": 380299, "values": [{"value": "Test"}]}]
        _update_lead_fields(lead_id=100, custom_fields=fields)
        assert mock_patch.called

    @patch("src.microservice.cron_yadisk.requests.patch")
    def test_api_error_logged(self, mock_patch):
        """API error is logged but doesn't raise."""
        from src.microservice.cron_yadisk import _update_lead_fields

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Server Error"
        mock_patch.return_value = mock_resp

        fields = [{"field_id": 380299, "values": [{"value": "Test"}]}]
        _update_lead_fields(lead_id=100, custom_fields=fields)

    @patch("src.microservice.cron_yadisk.requests.patch")
    def test_connection_error_handled(self, mock_patch):
        """Connection error is handled gracefully."""
        from src.microservice.cron_yadisk import _update_lead_fields

        mock_patch.side_effect = Exception("Network error")

        fields = [{"field_id": 380299, "values": [{"value": "Test"}]}]
        _update_lead_fields(lead_id=100, custom_fields=fields)


class TestMarkTenderProcessed:
    """Tests for mark_tender_processed function (correct signature)."""

    def test_marks_tender_in_db(self, db_conn):
        """Inserts a tender record into the database."""
        from src.microservice.cron_yadisk import mark_tender_processed

        row_id = mark_tender_processed(
            conn=db_conn,
            folder_path="/ТОРГИ/2024/Test Tender",
            folder_name="Test Tender",
            date_folder="2024",
            file_count=3,
            total_size=1024000,
            status="pending",
        )
        assert row_id > 0

        cursor = db_conn.execute(
            "SELECT folder_name, status FROM processed_tenders WHERE folder_path = ?",
            ("/ТОРГИ/2024/Test Tender",)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "Test Tender"
        assert row[1] == "pending"

    def test_marks_with_lead_id(self, db_conn):
        """Inserts a tender with amo_lead_id."""
        from src.microservice.cron_yadisk import mark_tender_processed

        row_id = mark_tender_processed(
            conn=db_conn,
            folder_path="/ТОРГИ/2024/Another",
            folder_name="Another",
            date_folder="2024",
            file_count=5,
            total_size=2048000,
            status="done",
            amo_lead_id=100,
            llm_result="classified as tender",
        )
        assert row_id > 0

        cursor = db_conn.execute(
            "SELECT amo_lead_id, status, llm_result FROM processed_tenders WHERE folder_path = ?",
            ("/ТОРГИ/2024/Another",)
        )
        row = cursor.fetchone()
        assert row[0] == 100
        assert row[1] == "done"
        assert "classified" in row[2]

    def test_marks_with_error(self, db_conn):
        """Inserts a tender with error status."""
        from src.microservice.cron_yadisk import mark_tender_processed

        row_id = mark_tender_processed(
            conn=db_conn,
            folder_path="/ТОРГИ/2024/Failed",
            folder_name="Failed",
            date_folder="2024",
            file_count=1,
            total_size=100,
            status="error",
            error="Download failed",
        )
        assert row_id > 0

        cursor = db_conn.execute(
            "SELECT status, error FROM processed_tenders WHERE folder_path = ?",
            ("/ТОРГИ/2024/Failed",)
        )
        row = cursor.fetchone()
        assert row[0] == "error"
        assert row[1] == "Download failed"

    def test_replace_existing_tender(self, db_conn):
        """INSERT OR REPLACE replaces existing record with same path."""
        from src.microservice.cron_yadisk import mark_tender_processed

        mark_tender_processed(
            conn=db_conn,
            folder_path="/ТОРГИ/2024/Dup",
            folder_name="Dup",
            date_folder="2024",
            file_count=1,
            total_size=100,
            status="pending",
        )
        # Insert again with same path
        mark_tender_processed(
            conn=db_conn,
            folder_path="/ТОРГИ/2024/Dup",
            folder_name="Dup",
            date_folder="2024",
            file_count=2,
            total_size=200,
            status="done",
        )

        cursor = db_conn.execute(
            "SELECT file_count, status FROM processed_tenders WHERE folder_path = ?",
            ("/ТОРГИ/2024/Dup",)
        )
        row = cursor.fetchone()
        assert row[0] == 2
        assert row[1] == "done"


class TestUpdateTenderStatus:
    """Tests for update_tender_status function."""

    def test_updates_status(self, db_conn):
        """Updates status of existing tender."""
        from src.microservice.cron_yadisk import mark_tender_processed, update_tender_status

        mark_tender_processed(
            conn=db_conn,
            folder_path="/ТОРГИ/2024/Update",
            folder_name="Update",
            date_folder="2024",
            file_count=1,
            total_size=100,
            status="pending",
        )

        update_tender_status(
            conn=db_conn,
            folder_path="/ТОРГИ/2024/Update",
            status="done",
            amo_lead_id=500,
        )

        cursor = db_conn.execute(
            "SELECT status, amo_lead_id FROM processed_tenders WHERE folder_path = ?",
            ("/ТОРГИ/2024/Update",)
        )
        row = cursor.fetchone()
        assert row[0] == "done"
        assert row[1] == 500

    def test_updates_with_llm_result(self, db_conn):
        """Updates status with LLM result."""
        from src.microservice.cron_yadisk import mark_tender_processed, update_tender_status

        mark_tender_processed(
            conn=db_conn,
            folder_path="/ТОРГИ/2024/LLM",
            folder_name="LLM",
            date_folder="2024",
            file_count=1,
            total_size=100,
            status="pending",
        )

        update_tender_status(
            conn=db_conn,
            folder_path="/ТОРГИ/2024/LLM",
            status="classified",
            llm_result='{"category": "tender", "confidence": 0.95}',
        )

        cursor = db_conn.execute(
            "SELECT status, llm_result FROM processed_tenders WHERE folder_path = ?",
            ("/ТОРГИ/2024/LLM",)
        )
        row = cursor.fetchone()
        assert row[0] == "classified"
        assert "tender" in row[1]

    def test_updates_with_error(self, db_conn):
        """Updates status with error message."""
        from src.microservice.cron_yadisk import mark_tender_processed, update_tender_status

        mark_tender_processed(
            conn=db_conn,
            folder_path="/ТОРГИ/2024/Err",
            folder_name="Err",
            date_folder="2024",
            file_count=1,
            total_size=100,
            status="pending",
        )

        update_tender_status(
            conn=db_conn,
            folder_path="/ТОРГИ/2024/Err",
            status="error",
            error="Classification failed: timeout",
        )

        cursor = db_conn.execute(
            "SELECT status, error FROM processed_tenders WHERE folder_path = ?",
            ("/ТОРГИ/2024/Err",)
        )
        row = cursor.fetchone()
        assert row[0] == "error"
        assert "timeout" in row[1]


class TestExtractCustomerFromFolderName:
    """Tests for _extract_customer_from_folder_name helper."""

    def test_extract_simple_name(self):
        """Extract customer from simple folder name with separator."""
        from src.microservice.cron_yadisk import _extract_customer_from_folder_name

        result = _extract_customer_from_folder_name("ООО Рога и Копыта - Тендер 123")
        assert result == "ООО Рога и Копыта"

    def test_extract_from_complex_name(self):
        """Extract customer from complex folder name."""
        from src.microservice.cron_yadisk import _extract_customer_from_folder_name

        result = _extract_customer_from_folder_name("АО НПП ИСТОК ШОКИНА - Не интересно - Калибры")
        assert result == "АО НПП ИСТОК ШОКИНА"

    def test_no_separator_returns_full_name(self):
        """No separator returns the full name stripped."""
        from src.microservice.cron_yadisk import _extract_customer_from_folder_name

        result = _extract_customer_from_folder_name("ООО Газпром Нефть")
        assert result == "ООО Газпром Нефть"

    def test_empty_string(self):
        """Empty string returns empty string."""
        from src.microservice.cron_yadisk import _extract_customer_from_folder_name

        result = _extract_customer_from_folder_name("")
        assert result == ""

    def test_single_separator(self):
        """Single separator splits correctly."""
        from src.microservice.cron_yadisk import _extract_customer_from_folder_name

        result = _extract_customer_from_folder_name("Gesac - 86 поз.")
        assert result == "Gesac"


class TestRunYadiskScanDeeper:
    """Deeper tests for run_yadisk_scan covering error/edge paths."""

    @patch("src.microservice.cron_yadisk.YADISK_TOKEN", "")
    def test_no_token_returns_error(self):
        """No YADISK_TOKEN returns error dict."""
        from src.microservice.cron_yadisk import run_yadisk_scan

        result = run_yadisk_scan(dry_run=True)
        assert "error" in result

    @patch("src.microservice.cron_yadisk.YADISK_TOKEN", "test_token")
    @patch("src.microservice.cron_yadisk.scan_root_folder")
    @patch("src.microservice.cron_yadisk.init_db")
    @patch("src.microservice.deduplication.DeduplicationDB")
    @patch("src.microservice.deduplication.TenderDeduplicator")
    @patch("src.microservice.cron_yadisk.YaDiskClient")
    def test_empty_scan_returns_zero_stats(self, mock_client_cls, mock_dedup_cls,
                                           mock_dedup_db_cls, mock_init_db, mock_scan):
        """Empty scan returns zero stats."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_conn = MagicMock()
        mock_init_db.return_value = mock_conn
        mock_scan.return_value = []

        from src.microservice.cron_yadisk import run_yadisk_scan
        result = run_yadisk_scan(dry_run=True)
        assert result.get("total_scanned", 0) == 0

    @patch("src.microservice.cron_yadisk.YADISK_TOKEN", "test_token")
    @patch("src.microservice.cron_yadisk.YaDiskClient")
    @patch("src.microservice.cron_yadisk.init_db")
    def test_db_init_called(self, mock_init_db, mock_client_cls):
        """Database is initialized on scan start."""
        mock_conn = MagicMock()
        mock_init_db.return_value = mock_conn
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch("src.microservice.cron_yadisk.scan_root_folder", return_value=[]):
            with patch("src.microservice.deduplication.DeduplicationDB"):
                with patch("src.microservice.deduplication.TenderDeduplicator"):
                    from src.microservice.cron_yadisk import run_yadisk_scan
                    run_yadisk_scan(dry_run=True)
                    mock_init_db.assert_called_once()


class TestFormatEnrichmentNote:
    """Tests for format_enrichment_note from deduplication.py."""

    def test_basic_format(self):
        """Basic enrichment note formatting."""
        from src.microservice.deduplication import format_enrichment_note, DeduplicationResult

        result = DeduplicationResult(
            is_enrichment=True,
            message="Обогащение выполнено",
            existing_lead_id=100,
            unchanged_files=[],
        )
        note = format_enrichment_note(result)
        assert "Обогащение выполнено" in note

    def test_with_field_changes(self):
        """Note includes field changes."""
        from src.microservice.deduplication import format_enrichment_note, DeduplicationResult

        result = DeduplicationResult(
            is_enrichment=True,
            message="Обогащение выполнено",
            existing_lead_id=100,
            unchanged_files=[],
        )
        old_fields = {"Заказчик": "Старый", "НМЦ": "100000"}
        new_fields = {"Заказчик": "Новый", "НМЦ": "200000"}

        note = format_enrichment_note(result, old_fields=old_fields, new_fields=new_fields)
        assert "Обновлены поля" in note
        assert "Заказчик" in note
        assert "Новый" in note

    def test_with_unchanged_files(self):
        """Note mentions unchanged files count."""
        from src.microservice.deduplication import format_enrichment_note, DeduplicationResult

        result = DeduplicationResult(
            is_enrichment=True,
            message="Обогащение",
            existing_lead_id=100,
            unchanged_files=["file1.pdf", "file2.xlsx", "file3.doc"],
        )
        note = format_enrichment_note(result)
        assert "3" in note

    def test_no_changes(self):
        """Note with no field changes and no unchanged files."""
        from src.microservice.deduplication import format_enrichment_note, DeduplicationResult

        result = DeduplicationResult(
            is_new=True,
            message="Новый тендер",
            unchanged_files=[],
        )
        note = format_enrichment_note(result)
        assert "Новый тендер" in note
