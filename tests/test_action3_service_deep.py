"""
Глубокие тесты для src/application/action3_service.py.
Покрывает: extract_link, process_note, _download_files, _classify_files, _update_lead.
"""
import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

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


@pytest.fixture
def action3_service():
    """Create Action3Service with mocked dependencies."""
    mock_amo = MagicMock()
    mock_yadisk = MagicMock()
    from src.application.action3_service import Action3Service
    service = Action3Service(amo_client=mock_amo, yadisk_client=mock_yadisk)
    return service, mock_amo, mock_yadisk


class TestExtractLink:
    """Tests for Action3Service.extract_link."""

    def test_yandex_disk_public_link(self, action3_service):
        service, _, _ = action3_service
        text = "Вот ссылка: https://disk.yandex.ru/d/abc123_XYZ на файлы"
        result = service.extract_link(text)
        assert result == "https://disk.yandex.ru/d/abc123_XYZ"

    def test_yadi_sk_link(self, action3_service):
        service, _, _ = action3_service
        text = "Файлы тут: https://yadi.sk/d/shortcode123"
        result = service.extract_link(text)
        assert result == "https://yadi.sk/d/shortcode123"

    def test_disk_internal_link(self, action3_service):
        service, _, _ = action3_service
        text = "Путь: disk:/ТОРГИ/Заказчик/файлы"
        result = service.extract_link(text)
        assert result == "disk:/ТОРГИ/Заказчик/файлы"

    def test_no_link_in_text(self, action3_service):
        service, _, _ = action3_service
        text = "Просто текст без ссылок"
        result = service.extract_link(text)
        assert result == ""

    def test_empty_text(self, action3_service):
        service, _, _ = action3_service
        result = service.extract_link("")
        assert result == ""

    def test_multiple_links_returns_first(self, action3_service):
        service, _, _ = action3_service
        text = "Ссылка 1: https://disk.yandex.ru/d/first и https://disk.yandex.ru/d/second"
        result = service.extract_link(text)
        assert result == "https://disk.yandex.ru/d/first"

    def test_link_with_special_chars(self, action3_service):
        service, _, _ = action3_service
        text = "https://disk.yandex.ru/d/abc-123_XYZ"
        result = service.extract_link(text)
        assert result == "https://disk.yandex.ru/d/abc-123_XYZ"


class TestProcessNote:
    """Tests for Action3Service.process_note."""

    def test_no_link_returns_ignored(self, action3_service):
        service, mock_amo, _ = action3_service
        result = service.process_note(42, "Просто текст без ссылки")
        assert result == {"status": "ignored", "reason": "no_link"}
        mock_amo.add_note.assert_not_called()

    def test_link_found_download_fails(self, action3_service):
        service, mock_amo, mock_yadisk = action3_service
        mock_yadisk.get_public_folder_items.return_value = []

        result = service.process_note(42, "https://disk.yandex.ru/d/abc123")
        assert result == {"status": "error", "reason": "download_failed"}
        # Should have added initial note
        assert mock_amo.add_note.call_count >= 1

    @patch("src.application.action3_service.shutil.rmtree")
    @patch("src.application.action3_service.tempfile.mkdtemp")
    def test_link_found_download_success(self, mock_mkdtemp, mock_rmtree, action3_service):
        service, mock_amo, mock_yadisk = action3_service
        mock_mkdtemp.return_value = "/tmp/action3_42_test"

        # Mock download success
        mock_yadisk.get_public_folder_items.return_value = [
            {"type": "file", "name": "doc.pdf", "path": "/doc.pdf"}
        ]
        mock_yadisk.get_public_download_url.return_value = "https://download.example.com"
        mock_yadisk.download_file.return_value = True

        # Mock classify
        with patch.object(service, "_classify_files", return_value={
            "customer": "ООО Заказчик",
            "priority": "Р2 — Высокий",
            "direction": "Спецоснастка",
            "situation_type": "Стандарт",
            "nmc": "5000000",
            "deadline": "2025-07-01"
        }):
            with patch.object(service, "_update_lead"):
                result = service.process_note(42, "https://disk.yandex.ru/d/abc123")
        assert result == {"status": "ok", "action": "processed"}
        mock_rmtree.assert_called_once()


class TestDownloadFiles:
    """Tests for Action3Service._download_files."""

    def test_public_link_downloads(self, action3_service):
        service, _, mock_yadisk = action3_service
        mock_yadisk.get_public_folder_items.return_value = [
            {"type": "file", "name": "doc.pdf", "path": "/doc.pdf"},
            {"type": "dir", "name": "subdir", "path": "/subdir"},
        ]
        mock_yadisk.get_public_download_url.return_value = "https://download.example.com"

        result = service._download_files("https://disk.yandex.ru/d/abc123", "/tmp/test")
        assert result is True
        mock_yadisk.download_file.assert_called_once()

    def test_internal_disk_link(self, action3_service):
        service, _, mock_yadisk = action3_service
        mock_yadisk.get_folder_items.return_value = [
            {"type": "file", "name": "tender.docx", "path": "/ТОРГИ/tender.docx"}
        ]
        mock_yadisk.get_download_url.return_value = "https://download.example.com"

        result = service._download_files("disk:/ТОРГИ/tender.docx", "/tmp/test")
        assert result is True
        mock_yadisk.download_file.assert_called_once()

    def test_empty_folder(self, action3_service):
        service, _, mock_yadisk = action3_service
        mock_yadisk.get_public_folder_items.return_value = []

        result = service._download_files("https://disk.yandex.ru/d/empty", "/tmp/test")
        assert result is False

    def test_internal_empty_folder(self, action3_service):
        service, _, mock_yadisk = action3_service
        mock_yadisk.get_folder_items.return_value = []

        result = service._download_files("disk:/empty", "/tmp/test")
        assert result is False


class TestClassifyFiles:
    """Tests for Action3Service._classify_files."""

    def test_no_extract_module_returns_defaults(self, action3_service):
        service, _, _ = action3_service
        with patch("src.application.action3_service.extract_file", None):
            with patch("src.application.action3_service.parse_tender_fields", None):
                result = service._classify_files("/tmp/test", ["doc.pdf"])
        assert result["priority"] == "Р4 — Наблюдаем"
        assert result["direction"] == "Не наш ассортимент"

    def test_with_extract_module(self, action3_service):
        service, _, _ = action3_service
        mock_extract = MagicMock(return_value=("Текст документа", None))
        mock_parse = MagicMock(return_value={
            "customer": "ООО Тест",
            "priority": "Р2",
            "direction": "Спецоснастка"
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            with open(os.path.join(tmpdir, "test.pdf"), "w") as f:
                f.write("test")

            with patch("src.application.action3_service.extract_file", mock_extract):
                with patch("src.application.action3_service.parse_tender_fields", mock_parse):
                    with patch("src.application.action3_service.validate_and_ocr_fallback", None):
                        result = service._classify_files(tmpdir, ["test.pdf"])
        assert result["customer"] == "ООО Тест"
        mock_extract.assert_called_once()
        mock_parse.assert_called_once()

    def test_with_ocr_fallback(self, action3_service):
        service, _, _ = action3_service
        mock_extract = MagicMock(return_value=("Текст", None))
        mock_parse = MagicMock(return_value={"customer": "Тест"})
        mock_validate = MagicMock(return_value={"customer": "Тест Validated"})

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "test.pdf"), "w") as f:
                f.write("test")

            with patch("src.application.action3_service.extract_file", mock_extract):
                with patch("src.application.action3_service.parse_tender_fields", mock_parse):
                    with patch("src.application.action3_service.validate_and_ocr_fallback", mock_validate):
                        result = service._classify_files(tmpdir, ["test.pdf"])
        assert result["customer"] == "Тест Validated"
        mock_validate.assert_called_once()


class TestUpdateLead:
    """Tests for Action3Service._update_lead."""

    def test_updates_lead_with_all_fields(self, action3_service):
        service, mock_amo, _ = action3_service
        result = {
            "customer": "ООО Заказчик",
            "priority": "Р2 — Высокий",
            "direction": "Спецоснастка",
            "situation_type": "Стандарт",
            "nmc": "5000000",
            "deadline": "2025-07-01"
        }

        with patch("src.application.action3_service.resolve_routing", return_value=(100002, 999)):
            with patch("src.application.action3_service.build_lead_name", return_value="Р2 | ООО Заказчик"):
                service._update_lead(42, result)
        mock_amo.update_lead.assert_called_once()
        mock_amo.add_note.assert_called_once()
        # Check custom_fields were passed
        call_kwargs = mock_amo.update_lead.call_args
        assert call_kwargs[1]["lead_id"] == 42
        assert call_kwargs[1]["status_id"] == 100002
        assert call_kwargs[1]["responsible_user_id"] == 999

    def test_updates_lead_without_optional_fields(self, action3_service):
        service, mock_amo, _ = action3_service
        result = {
            "priority": "Р4 — Наблюдаем",
            "direction": "Не наш ассортимент",
            "situation_type": "Стандарт",
        }

        with patch("src.application.action3_service.resolve_routing", return_value=(100002, 999)):
            with patch("src.application.action3_service.build_lead_name", return_value="Р4 | Неизвестно"):
                service._update_lead(42, result)
        mock_amo.update_lead.assert_called_once()
        # custom_fields should have priority, direction, situation_type but not nmc/deadline
        call_kwargs = mock_amo.update_lead.call_args[1]
        custom_fields = call_kwargs["custom_fields"]
        # At least 3 fields (priority, direction, situation_type)
        assert len(custom_fields) >= 3

    def test_report_note_contains_info(self, action3_service):
        service, mock_amo, _ = action3_service
        result = {
            "customer": "ООО Тест",
            "priority": "Р1",
            "direction": "ВСС",
            "situation_type": "Стандарт",
            "nmc": "1000000",
            "deadline": "2025-08-01"
        }

        with patch("src.application.action3_service.resolve_routing", return_value=(100002, 999)):
            with patch("src.application.action3_service.build_lead_name", return_value="Р1 | ООО Тест"):
                service._update_lead(42, result)
        note_text = mock_amo.add_note.call_args[0][1]
        assert "ООО Тест" in note_text
        assert "1000000" in note_text
        assert "ВСС" in note_text
