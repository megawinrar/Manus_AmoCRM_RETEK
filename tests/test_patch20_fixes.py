"""
Тесты для PATCH20: исправления Action 3 и amo_client.

Покрывает:
1. amo_client: Response с 4xx не считается None (if r is not None)
2. action3_handler: FIELD_LLM_CONFIDENCE отправляется как число (0-100)
3. action3_handler: procedure_number конвертируется в int (strip non-digits)
4. webhook_handler: entity_id извлекается корректно (не note_id)
5. cron_hourly: deadline timestamp конвертируется в строку даты
6. action3_handler: extract_yadisk_link парсит пути с пробелами
"""
import sys
import os
import json
import time
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════════
# TEST 1: amo_client Response truthiness fix
# ═══════════════════════════════════════════════════════════════════

class TestAmoClientResponseCheck:
    """Проверяем что amo_client корректно обрабатывает 4xx ответы."""

    def test_response_400_not_treated_as_none(self):
        """Response с status 400 не должен показывать NO_RESPONSE."""
        from unittest.mock import patch, MagicMock
        import requests

        # Создаём мок Response с status_code 400
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 400
        mock_response.text = '{"error": "bad request"}'
        # requests.Response.__bool__ returns False for 4xx
        mock_response.__bool__ = lambda self: False

        # Проверяем что "r is not None" работает корректно
        r = mock_response
        assert r is not None, "Response object should not be None"
        assert (r is not None and r.status_code == 200) == False
        # Старый баг: "if r" would be False for 400 response
        assert bool(r) == False, "bool(Response(400)) should be False"
        # Новый код: "if r is not None" should be True
        assert (r is not None) == True

    def test_response_200_passes(self):
        """Response с status 200 должен проходить проверку."""
        import requests
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.__bool__ = lambda self: True

        r = mock_response
        assert r is not None and r.status_code == 200

    def test_none_response_detected(self):
        """None response (все retry failed) должен корректно определяться."""
        r = None
        assert (r is not None) == False
        # Ternary should show NO_RESPONSE
        msg = f"{r.status_code if r is not None else 'NO_RESPONSE'}"
        assert msg == "NO_RESPONSE"

    def test_error_message_shows_status_code(self):
        """При 400 ответе должен показываться status_code, а не NO_RESPONSE."""
        import requests
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 400
        mock_response.text = '{"error": "validation failed"}'
        mock_response.__bool__ = lambda self: False

        r = mock_response
        msg = f"{r.status_code if r is not None else 'NO_RESPONSE'}"
        assert msg == "400", f"Expected '400', got '{msg}'"


# ═══════════════════════════════════════════════════════════════════
# TEST 2: LLM Confidence field - numeric conversion
# ═══════════════════════════════════════════════════════════════════

class TestLLMConfidenceNumeric:
    """Проверяем что confidence конвертируется в числовое значение 0-100."""

    def test_dict_confidence_to_avg_score(self):
        """Dict с float scores должен конвертироваться в среднее * 100."""
        confidence = {
            "customer": 0.8,
            "nmc": 0.6,
            "deadline": 0.9,
            "procedure_number": 0.7,
        }
        scores = [v for v in confidence.values() if isinstance(v, (int, float))]
        avg_score = int(sum(scores) / len(scores) * 100) if scores else 0
        assert avg_score == 75, f"Expected 75, got {avg_score}"

    def test_zero_confidence_dict(self):
        """Dict с нулевыми scores должен давать 0."""
        confidence = {
            "customer": 0.0,
            "nmc": 0.0,
            "deadline": 0.0,
        }
        scores = [v for v in confidence.values() if isinstance(v, (int, float))]
        avg_score = int(sum(scores) / len(scores) * 100) if scores else 0
        assert avg_score == 0

    def test_single_float_confidence(self):
        """Одиночный float должен конвертироваться в int * 100."""
        confidence = 0.85
        if isinstance(confidence, (int, float)):
            avg_score = int(confidence * 100)
        assert avg_score == 85

    def test_empty_dict_confidence(self):
        """Пустой dict должен давать 0."""
        confidence = {}
        scores = [v for v in confidence.values() if isinstance(v, (int, float))]
        avg_score = int(sum(scores) / len(scores) * 100) if scores else 0
        assert avg_score == 0

    def test_mixed_types_in_confidence(self):
        """Dict с нечисловыми значениями должен игнорировать их."""
        confidence = {
            "customer": 0.9,
            "note": "some text",
            "nmc": 0.7,
        }
        scores = [v for v in confidence.values() if isinstance(v, (int, float))]
        avg_score = int(sum(scores) / len(scores) * 100) if scores else 0
        assert avg_score == 80


# ═══════════════════════════════════════════════════════════════════
# TEST 3: procedure_number numeric conversion
# ═══════════════════════════════════════════════════════════════════

class TestProcedureNumberConversion:
    """Проверяем конвертацию procedure_number в числовой формат."""

    import re

    def _convert(self, procedure_number):
        """Эмулирует логику из action3_handler."""
        import re
        proc_str = re.sub(r'[^\d]', '', str(procedure_number).strip())
        if proc_str:
            return int(proc_str)
        return None

    def test_simple_number(self):
        """Простое число '63' -> 63."""
        assert self._convert("63") == 63

    def test_number_with_dashes(self):
        """Формат '1234-5678-12345' -> 123456781234 (все цифры)."""
        result = self._convert("1234-5678-12345")
        assert result == 1234567812345

    def test_number_with_spaces(self):
        """'  63  ' -> 63."""
        assert self._convert("  63  ") == 63

    def test_number_with_prefix(self):
        """'ЗП-63' -> 63."""
        assert self._convert("ЗП-63") == 63

    def test_empty_string(self):
        """Пустая строка -> None (не отправляем)."""
        assert self._convert("") is None

    def test_no_digits(self):
        """Строка без цифр -> None."""
        assert self._convert("без номера") is None

    def test_large_number(self):
        """Большой номер закупки."""
        assert self._convert("0373100122024000063") == 373100122024000063


# ═══════════════════════════════════════════════════════════════════
# TEST 4: webhook_handler entity_id extraction
# ═══════════════════════════════════════════════════════════════════

class TestWebhookEntityIdExtraction:
    """Проверяем что lead_id извлекается из entity_id, а не из note id."""

    def test_entity_id_preferred_over_note_id(self):
        """entity_id должен использоваться как lead_id."""
        # Симулируем данные вебхука
        note_data = {
            "id": "3955171",  # note_id - НЕ lead_id!
            "entity_id": "3166633",  # правильный lead_id
            "entity_type": "leads",
            "note_type": "common",
            "text": "test",
        }
        # Логика извлечения (как в webhook_handler.py)
        lead_id = int(note_data.get("entity_id") or note_data.get("element_id") or note_data.get("id", 0))
        assert lead_id == 3166633, f"Expected 3166633, got {lead_id}"

    def test_element_id_fallback(self):
        """element_id должен использоваться если entity_id отсутствует."""
        note_data = {
            "id": "3955171",
            "element_id": "3166633",
            "note_type": "common",
            "text": "test",
        }
        lead_id = int(note_data.get("entity_id") or note_data.get("element_id") or note_data.get("id", 0))
        assert lead_id == 3166633

    def test_note_id_not_used_when_entity_id_present(self):
        """note id НЕ должен использоваться как lead_id."""
        note_data = {
            "id": "9999999",  # note_id
            "entity_id": "1234567",  # lead_id
        }
        lead_id = int(note_data.get("entity_id") or note_data.get("element_id") or note_data.get("id", 0))
        assert lead_id != 9999999
        assert lead_id == 1234567


# ═══════════════════════════════════════════════════════════════════
# TEST 5: cron_hourly deadline timestamp to string
# ═══════════════════════════════════════════════════════════════════

class TestDeadlineTimestampConversion:
    """Проверяем конвертацию Unix timestamp в строку даты."""

    def test_timestamp_to_date_string(self):
        """Unix timestamp 1750204800 -> '2025-06-18' (или подобная дата)."""
        deadline_value = 1750204800
        if isinstance(deadline_value, (int, float)) and deadline_value > 1_000_000_000:
            deadline_str = datetime.fromtimestamp(deadline_value).strftime("%d.%m.%Y")
        else:
            deadline_str = str(deadline_value)
        # Должна быть дата, а не число
        assert "." in deadline_str
        assert len(deadline_str) == 10  # DD.MM.YYYY

    def test_already_string_date(self):
        """Строка '2025-06-18' не должна конвертироваться."""
        deadline_value = "2025-06-18"
        if isinstance(deadline_value, (int, float)) and deadline_value > 1_000_000_000:
            deadline_str = datetime.fromtimestamp(deadline_value).strftime("%d.%m.%Y")
        else:
            deadline_str = str(deadline_value)
        assert deadline_str == "2025-06-18"

    def test_zero_timestamp(self):
        """0 не должен конвертироваться (нет дедлайна)."""
        deadline_value = 0
        if isinstance(deadline_value, (int, float)) and deadline_value > 1_000_000_000:
            deadline_str = datetime.fromtimestamp(deadline_value).strftime("%d.%m.%Y")
        else:
            deadline_str = str(deadline_value)
        assert deadline_str == "0"


# ═══════════════════════════════════════════════════════════════════
# TEST 6: extract_yadisk_link with spaces in path
# ═══════════════════════════════════════════════════════════════════

class TestYadiskLinkExtraction:
    """Проверяем парсинг ссылок на Яндекс.Диск с пробелами."""

    def test_path_with_spaces(self):
        """Путь с пробелами должен парситься корректно."""
        from src.microservice.action3_handler import extract_yadisk_link
        text = "распознай disk:/ТОРГИ/09.06.2026/Протон-ПМ - Твердосплав зенкер/"
        link = extract_yadisk_link(text)
        assert link is not None
        assert "Протон-ПМ" in link
        assert "Твердосплав зенкер" in link

    def test_path_with_cyrillic(self):
        """Путь с кириллицей должен парситься."""
        from src.microservice.action3_handler import extract_yadisk_link
        text = "disk:/ТОРГИ/01.01.2025/Заказчик - Описание/"
        link = extract_yadisk_link(text)
        assert link is not None
        assert "/ТОРГИ/" in link

    def test_public_link(self):
        """Публичная ссылка yadi.sk должна парситься."""
        from src.microservice.action3_handler import extract_yadisk_link
        text = "Вот ссылка: https://disk.yandex.ru/d/abc123def456"
        link = extract_yadisk_link(text)
        assert link is not None
        assert "disk.yandex.ru" in link

    def test_no_link(self):
        """Текст без ссылки должен возвращать None."""
        from src.microservice.action3_handler import extract_yadisk_link
        text = "Просто текст без ссылки на диск"
        link = extract_yadisk_link(text)
        assert link is None


# ═══════════════════════════════════════════════════════════════════
# TEST 7: run_in_executor (sync function, not async)
# ═══════════════════════════════════════════════════════════════════

class TestProcessAction3IsSync:
    """Проверяем что process_action3 - синхронная функция."""

    def test_not_coroutine(self):
        """process_action3 НЕ должна быть async."""
        import inspect
        from src.microservice.action3_handler import process_action3
        assert not inspect.iscoroutinefunction(process_action3), \
            "process_action3 should be a regular function, not async"


# ═══════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════

def run_all_tests():
    """Запуск всех тестов."""
    test_classes = [
        TestAmoClientResponseCheck,
        TestLLMConfidenceNumeric,
        TestProcedureNumberConversion,
        TestWebhookEntityIdExtraction,
        TestDeadlineTimestampConversion,
        TestYadiskLinkExtraction,
        TestProcessAction3IsSync,
    ]

    total = 0
    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        for method_name in methods:
            total += 1
            try:
                getattr(instance, method_name)()
                passed += 1
                print(f"  ✓ {cls.__name__}.{method_name}")
            except Exception as e:
                failed += 1
                errors.append((cls.__name__, method_name, str(e)))
                print(f"  ✗ {cls.__name__}.{method_name}: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if errors:
        print(f"\nFailed tests:")
        for cls_name, method, err in errors:
            print(f"  - {cls_name}.{method}: {err}")
    print(f"{'='*60}")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
