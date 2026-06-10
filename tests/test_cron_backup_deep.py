"""
Глубокие тесты для src/microservice/cron_backup.py.
Покрывает: fetch_all_leads, fetch_lead_notes, fetch_tasks, save_backup_local,
save_backup_yadisk, _rotate_backups, save_lead_snapshot, run_backup.
"""
import os
import sys
import json
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime
from pathlib import Path

os.environ.setdefault("AMO_DOMAIN", "tokutools.amocrm.ru")
os.environ.setdefault("AMO_ACCESS_TOKEN", "test_access_token")
os.environ.setdefault("AMO_REFRESH_TOKEN", "test_refresh_token")
os.environ.setdefault("AMO_CLIENT_ID", "test_client_id")
os.environ.setdefault("AMO_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("AMO_TOKEN_EXPIRES_AT", "9999999999")
os.environ.setdefault("YANDEX_GPT_API_KEY", "test_key")
os.environ.setdefault("YANDEX_GPT_FOLDER_ID", "test_folder")
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
os.environ.setdefault("AMO_PIPELINE_ACTIVE_ID", "1")
os.environ.setdefault("AMO_PIPELINE_ARCHIVE_DIRECTIONS_ID", "2")
os.environ.setdefault("AMO_PIPELINE_ARCHIVE_SOZ_ID", "3")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestFetchAllLeads:
    """Tests for fetch_all_leads."""

    @patch("src.microservice.cron_backup.requests.get")
    def test_empty_response_204(self, mock_get):
        """204 response means no data."""
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_get.return_value = mock_resp

        from src.microservice.cron_backup import fetch_all_leads
        result = fetch_all_leads(with_notes=False)
        assert result == []

    @patch("src.microservice.cron_backup.requests.get")
    def test_error_response(self, mock_get):
        """Non-200 response stops fetching."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_get.return_value = mock_resp

        from src.microservice.cron_backup import fetch_all_leads
        result = fetch_all_leads(with_notes=False)
        assert result == []

    @patch("src.microservice.cron_backup.time.sleep")
    @patch("src.microservice.cron_backup.requests.get")
    def test_single_page_of_leads(self, mock_get, mock_sleep):
        """Single page of leads returned."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {"leads": [{"id": 1}, {"id": 2}]},
            "_links": {}
        }
        mock_get.return_value = mock_resp

        from src.microservice.cron_backup import fetch_all_leads
        result = fetch_all_leads(with_notes=False)
        assert len(result) == 2

    @patch("src.microservice.cron_backup.time.sleep")
    @patch("src.microservice.cron_backup.requests.get")
    def test_multi_page_leads(self, mock_get, mock_sleep):
        """Multiple pages of leads."""
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "_embedded": {"leads": [{"id": 1}]},
            "_links": {"next": {"href": "page2"}}
        }
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "_embedded": {"leads": [{"id": 2}]},
            "_links": {}
        }
        mock_get.side_effect = [resp1, resp2]

        from src.microservice.cron_backup import fetch_all_leads
        result = fetch_all_leads(with_notes=False)
        assert len(result) == 2

    @patch("src.microservice.cron_backup.fetch_lead_notes")
    @patch("src.microservice.cron_backup.time.sleep")
    @patch("src.microservice.cron_backup.requests.get")
    def test_with_notes(self, mock_get, mock_sleep, mock_notes):
        """Fetches notes for each lead when with_notes=True."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {"leads": [{"id": 1}, {"id": 2}]},
            "_links": {}
        }
        mock_get.return_value = mock_resp
        mock_notes.return_value = [{"id": 100, "text": "note"}]

        from src.microservice.cron_backup import fetch_all_leads
        result = fetch_all_leads(with_notes=True)
        assert len(result) == 2
        assert result[0]["_notes"] == [{"id": 100, "text": "note"}]
        assert mock_notes.call_count == 2


class TestFetchLeadNotes:
    """Tests for fetch_lead_notes."""

    @patch("src.microservice.cron_backup.requests.get")
    def test_no_notes_204(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_get.return_value = mock_resp

        from src.microservice.cron_backup import fetch_lead_notes
        result = fetch_lead_notes(123)
        assert result == []

    @patch("src.microservice.cron_backup.requests.get")
    def test_notes_returned(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {"notes": [{"id": 1, "text": "Hello"}]},
            "_links": {}
        }
        mock_get.return_value = mock_resp

        from src.microservice.cron_backup import fetch_lead_notes
        result = fetch_lead_notes(123)
        assert len(result) == 1

    @patch("src.microservice.cron_backup.requests.get")
    def test_notes_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        from src.microservice.cron_backup import fetch_lead_notes
        result = fetch_lead_notes(123)
        assert result == []

    @patch("src.microservice.cron_backup.requests.get")
    def test_notes_multi_page(self, mock_get):
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "_embedded": {"notes": [{"id": 1}]},
            "_links": {"next": {"href": "page2"}}
        }
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "_embedded": {"notes": [{"id": 2}]},
            "_links": {}
        }
        mock_get.side_effect = [resp1, resp2]

        from src.microservice.cron_backup import fetch_lead_notes
        result = fetch_lead_notes(123)
        assert len(result) == 2


class TestFetchTasks:
    """Tests for fetch_tasks."""

    @patch("src.microservice.cron_backup.time.sleep")
    @patch("src.microservice.cron_backup.requests.get")
    def test_no_tasks(self, mock_get, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_get.return_value = mock_resp

        from src.microservice.cron_backup import fetch_tasks
        result = fetch_tasks()
        assert result == []

    @patch("src.microservice.cron_backup.time.sleep")
    @patch("src.microservice.cron_backup.requests.get")
    def test_tasks_returned(self, mock_get, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "_embedded": {"tasks": [{"id": 1}, {"id": 2}]},
            "_links": {}
        }
        mock_get.return_value = mock_resp

        from src.microservice.cron_backup import fetch_tasks
        result = fetch_tasks()
        assert len(result) == 2


class TestSaveBackupLocal:
    """Tests for save_backup_local."""

    @patch("src.microservice.cron_backup._rotate_backups")
    def test_saves_json_file(self, mock_rotate):
        from src.microservice.cron_backup import save_backup_local
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.microservice.cron_backup.BACKUP_DIR", tmpdir):
                path = save_backup_local([{"id": 1}], [{"id": 10}])
            assert path.endswith(".json")
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert data["meta"]["leads_count"] == 1
            assert data["meta"]["tasks_count"] == 1
            assert len(data["leads"]) == 1

    @patch("src.microservice.cron_backup._rotate_backups")
    def test_saves_without_tasks(self, mock_rotate):
        from src.microservice.cron_backup import save_backup_local
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.microservice.cron_backup.BACKUP_DIR", tmpdir):
                path = save_backup_local([{"id": 1}], None)
            with open(path) as f:
                data = json.load(f)
            assert data["meta"]["tasks_count"] == 0
            assert data["tasks"] == []


class TestSaveBackupYadisk:
    """Tests for save_backup_yadisk."""

    @patch("src.microservice.cron_backup.YADISK_TOKEN", None)
    def test_no_token_returns_false(self):
        from src.microservice.cron_backup import save_backup_yadisk
        result = save_backup_yadisk("/tmp/test.json")
        assert result is False

    @patch("src.microservice.cron_backup.YADISK_TOKEN", "test_token")
    @patch("src.microservice.cron_backup.requests.put")
    @patch("src.microservice.cron_backup.requests.get")
    def test_upload_url_error(self, mock_get, mock_put):
        mock_get.return_value = MagicMock(status_code=500, text="Error")
        mock_put.return_value = MagicMock(status_code=201)

        from src.microservice.cron_backup import save_backup_yadisk
        result = save_backup_yadisk("/tmp/test.json")
        assert result is False

    @patch("src.microservice.cron_backup.YADISK_TOKEN", "test_token")
    @patch("builtins.open", mock_open(read_data=b"test data"))
    @patch("src.microservice.cron_backup.requests.put")
    @patch("src.microservice.cron_backup.requests.get")
    def test_successful_upload(self, mock_get, mock_put):
        # GET for upload URL
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"href": "https://upload.example.com"})
        )
        # PUT for folder creation and file upload
        mock_put.return_value = MagicMock(status_code=201)

        from src.microservice.cron_backup import save_backup_yadisk
        result = save_backup_yadisk("/tmp/test.json")
        assert result is True

    @patch("src.microservice.cron_backup.YADISK_TOKEN", "test_token")
    @patch("builtins.open", mock_open(read_data=b"test data"))
    @patch("src.microservice.cron_backup.requests.put")
    @patch("src.microservice.cron_backup.requests.get")
    def test_upload_fails(self, mock_get, mock_put):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"href": "https://upload.example.com"})
        )
        # First put is folder creation (ok), second is upload (fail)
        mock_put.side_effect = [MagicMock(status_code=201), MagicMock(status_code=500)]

        from src.microservice.cron_backup import save_backup_yadisk
        result = save_backup_yadisk("/tmp/test.json")
        assert result is False

    @patch("src.microservice.cron_backup.YADISK_TOKEN", "test_token")
    @patch("src.microservice.cron_backup.requests.put")
    @patch("src.microservice.cron_backup.requests.get")
    def test_no_href_in_response(self, mock_get, mock_put):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={})
        )
        mock_put.return_value = MagicMock(status_code=201)

        from src.microservice.cron_backup import save_backup_yadisk
        result = save_backup_yadisk("/tmp/test.json")
        assert result is False


class TestRotateBackups:
    """Tests for _rotate_backups."""

    def test_no_rotation_needed(self):
        from src.microservice.cron_backup import _rotate_backups
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create 3 files (under keep=30)
            for i in range(3):
                Path(tmpdir, f"backup_{i}.json").write_text("{}")
            _rotate_backups(tmpdir, keep=30)
            assert len(list(Path(tmpdir).glob("backup_*.json"))) == 3

    def test_rotation_deletes_old_files(self):
        from src.microservice.cron_backup import _rotate_backups
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create 5 files, keep only 3
            for i in range(5):
                p = Path(tmpdir, f"backup_{i:02d}.json")
                p.write_text("{}")
                time.sleep(0.01)  # Ensure different mtime
            _rotate_backups(tmpdir, keep=3)
            remaining = list(Path(tmpdir).glob("backup_*.json"))
            assert len(remaining) == 3


class TestSaveLeadSnapshot:
    """Tests for save_lead_snapshot."""

    @patch("src.microservice.cron_backup.fetch_lead_notes")
    @patch("src.microservice.cron_backup.requests.get")
    def test_successful_snapshot(self, mock_get, mock_notes):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"id": 42, "name": "Test"})
        )
        mock_notes.return_value = [{"id": 1}]

        from src.microservice.cron_backup import save_lead_snapshot
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.microservice.cron_backup.BACKUP_DIR", tmpdir):
                path = save_lead_snapshot(42, "before_enrichment")
            assert path != ""
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert data["meta"]["lead_id"] == 42
            assert data["meta"]["event"] == "before_enrichment"

    @patch("src.microservice.cron_backup.requests.get")
    def test_snapshot_api_error(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404)

        from src.microservice.cron_backup import save_lead_snapshot
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.microservice.cron_backup.BACKUP_DIR", tmpdir):
                path = save_lead_snapshot(42, "before_enrichment")
        assert path == ""


class TestRunBackup:
    """Tests for run_backup."""

    @patch("src.microservice.cron_backup.save_backup_yadisk")
    @patch("src.microservice.cron_backup.save_backup_local")
    @patch("src.microservice.cron_backup.fetch_tasks")
    @patch("src.microservice.cron_backup.fetch_all_leads")
    def test_full_backup(self, mock_leads, mock_tasks, mock_save_local, mock_save_yadisk):
        mock_leads.return_value = [{"id": 1}, {"id": 2}]
        mock_tasks.return_value = [{"id": 10}]
        mock_save_local.return_value = "/tmp/backup.json"
        mock_save_yadisk.return_value = True

        from src.microservice.cron_backup import run_backup
        result = run_backup(with_notes=True, upload_yadisk=True)
        assert result["leads_count"] == 2
        assert result["tasks_count"] == 1
        assert result["local_path"] == "/tmp/backup.json"
        mock_save_yadisk.assert_called_once()

    @patch("src.microservice.cron_backup.save_backup_yadisk")
    @patch("src.microservice.cron_backup.save_backup_local")
    @patch("src.microservice.cron_backup.fetch_tasks")
    @patch("src.microservice.cron_backup.fetch_all_leads")
    def test_backup_without_yadisk(self, mock_leads, mock_tasks, mock_save_local, mock_save_yadisk):
        mock_leads.return_value = [{"id": 1}]
        mock_tasks.return_value = []
        mock_save_local.return_value = "/tmp/backup.json"

        from src.microservice.cron_backup import run_backup
        result = run_backup(with_notes=False, upload_yadisk=False)
        assert result["leads_count"] == 1
        mock_save_yadisk.assert_not_called()
