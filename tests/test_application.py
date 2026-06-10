"""
Tests for application layer.
"""
import pytest
from unittest.mock import MagicMock, patch
from src.application.action3_service import Action3Service
from src.application.webhook_service import WebhookService


class TestAction3Service:
    def setup_method(self):
        self.amo = MagicMock()
        self.yadisk = MagicMock()
        self.service = Action3Service(self.amo, self.yadisk)

    def test_extract_link_public(self):
        text = "Вот ссылка https://disk.yandex.ru/d/abc123 на тендер"
        link = self.service.extract_link(text)
        assert link == "https://disk.yandex.ru/d/abc123"

    def test_extract_link_yadi_sk(self):
        text = "Файлы: https://yadi.sk/d/xyz789"
        link = self.service.extract_link(text)
        assert link == "https://yadi.sk/d/xyz789"

    def test_extract_link_internal_path(self):
        text = "Тендер disk:/ТОРГИ/09.06.2026/Gesac/"
        link = self.service.extract_link(text)
        assert link == "disk:/ТОРГИ/09.06.2026/Gesac/"

    def test_extract_link_no_link(self):
        text = "Просто текст без ссылки"
        link = self.service.extract_link(text)
        assert link == ""

    def test_process_note_no_link(self):
        result = self.service.process_note(123, "Просто текст")
        assert result["status"] == "ignored"
        assert result["reason"] == "no_link"


class TestWebhookService:
    def setup_method(self):
        self.amo = MagicMock()
        self.service = WebhookService(self.amo)

    def test_handle_lead_add_not_found(self):
        self.amo.get_lead.return_value = None
        result = self.service.handle_lead_add(123)
        assert result["status"] == "error"

    def test_handle_lead_add_wrong_status(self):
        self.amo.get_lead.return_value = {"status_id": 999999}
        result = self.service.handle_lead_add(123)
        assert result["status"] == "ignored"
        assert result["reason"] == "wrong_status"
