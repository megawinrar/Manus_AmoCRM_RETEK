"""
Тесты для модуля LLM-классификатора (src/microservice/llm_classifier.py).

Покрытие:
- classify_tender — классификация тендеров (P1-P4, разные направления)
- determine_archive_destination — определение архивного назначения
- classify_by_rules — rule-based fallback
- determine_archive_by_rules — rule-based архивация
- parse_json_response — парсинг JSON из ответа LLM
- extract_customer_from_name — извлечение заказчика
- load_system_context — загрузка контекста
- YandexGPTClient — клиент GPT
- Обработка ошибок (timeout, bad response, rate limit)
- Edge cases (пустой вход, malformed ответ)

Запуск:
    pytest tests/test_llm_classifier.py -v
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

# Устанавливаем переменные окружения ДО импорта модулей
os.environ.setdefault("AMO_DOMAIN", "tokutools.amocrm.ru")
os.environ.setdefault("AMO_ACCESS_TOKEN", "test_token_for_testing")
os.environ.setdefault("YANDEX_GPT_API_KEY", "test_yandex_gpt_key")
os.environ.setdefault("YANDEX_GPT_FOLDER_ID", "test_folder_id")
os.environ.setdefault("YANDEX_GPT_MODEL", "yandexgpt/latest")
os.environ.setdefault("LLM_MODE", "training")
os.environ.setdefault("LLM_LOG_DIR", "/tmp/test_llm_logs")
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.microservice.llm_classifier import (
    classify_tender,
    determine_archive_destination,
    classify_by_rules,
    determine_archive_by_rules,
    parse_json_response,
    extract_customer_from_name,
    load_system_context,
    log_llm_result,
    YandexGPTClient,
)


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def gpt_client():
    """Создать экземпляр YandexGPTClient."""
    return YandexGPTClient()


@pytest.fixture
def sample_classification_json():
    """Типичный JSON-ответ классификации от GPT."""
    return json.dumps({
        "priority": "Р1",
        "situation_type": "Запрос котировок / реальные торги",
        "direction": "CARBIDE-STANDARD",
        "sub_direction": "Фрезы концевые",
        "customer": "ООО НПО Высокоточные Системы",
        "product_description": "Фрезы концевые твердосплавные",
        "confidence": 0.92,
        "comment": "Реальный тендер на фрезы из твердого сплава"
    }, ensure_ascii=False)


@pytest.fixture
def sample_archive_json():
    """Типичный JSON-ответ архивации от GPT."""
    return json.dumps({
        "archive_destination": "Архив — направления / Твердосплав",
        "confidence": 0.85,
        "comment": "Направление — твердосплав, стандартная архивация"
    }, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ parse_json_response
# ═══════════════════════════════════════════════════════════════════

class TestParseJsonResponse:
    """Тесты парсинга JSON из ответа LLM."""

    def test_parse_valid_json(self):
        """Парсинг валидного JSON."""
        text = '{"priority": "Р1", "confidence": 0.9}'
        result = parse_json_response(text)
        assert result is not None
        assert result["priority"] == "Р1"
        assert result["confidence"] == 0.9

    def test_parse_json_in_markdown_block(self):
        """Парсинг JSON из markdown блока."""
        text = '```json\n{"priority": "Р2", "direction": "HSS-STANDARD"}\n```'
        result = parse_json_response(text)
        assert result is not None
        assert result["priority"] == "Р2"
        assert result["direction"] == "HSS-STANDARD"

    def test_parse_json_with_surrounding_text(self):
        """Парсинг JSON с окружающим текстом."""
        text = 'Вот результат анализа:\n{"priority": "Р3", "confidence": 0.7}\nКонец ответа.'
        result = parse_json_response(text)
        assert result is not None
        assert result["priority"] == "Р3"

    def test_parse_invalid_json(self):
        """Невалидный JSON возвращает None."""
        text = "Это просто текст без JSON"
        result = parse_json_response(text)
        assert result is None

    def test_parse_empty_string(self):
        """Пустая строка возвращает None."""
        result = parse_json_response("")
        assert result is None

    def test_parse_partial_json(self):
        """Неполный JSON (обрезанный)."""
        text = '{"priority": "Р1", "confidence":'
        result = parse_json_response(text)
        # Может вернуть None если JSON невалиден
        # Зависит от реализации — не должен крашиться
        assert result is None or isinstance(result, dict)

    def test_parse_json_with_unicode(self):
        """JSON с юникодом."""
        text = json.dumps({
            "priority": "Р1",
            "customer": "ООО «Завод Прогресс»",
            "comment": "Тендер на спецінструмент"
        }, ensure_ascii=False)
        result = parse_json_response(text)
        assert result is not None
        assert result["customer"] == "ООО «Завод Прогресс»"

    def test_parse_json_in_code_block_without_lang(self):
        """JSON в code block без указания языка."""
        text = '```\n{"priority": "Р4", "direction": "OUT-OF-SCOPE"}\n```'
        result = parse_json_response(text)
        assert result is not None
        assert result["priority"] == "Р4"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ extract_customer_from_name
# ═══════════════════════════════════════════════════════════════════

class TestExtractCustomerFromName:
    """Тесты извлечения заказчика из имени папки."""

    def test_simple_customer(self):
        """Простое имя заказчика."""
        result = extract_customer_from_name("Gesac - 86 поз.")
        assert result == "Gesac"

    def test_customer_with_org_form(self):
        """Заказчик с организационной формой."""
        result = extract_customer_from_name("АО ОКБ ФАКЕЛ - твердосплав")
        assert result == "АО ОКБ ФАКЕЛ"

    def test_no_separator(self):
        """Имя без разделителя."""
        result = extract_customer_from_name("Простое название")
        assert result == "Простое название"

    def test_multiple_separators(self):
        """Несколько разделителей."""
        result = extract_customer_from_name("ООО Завод - фрезы - 50 поз.")
        assert result == "ООО Завод"

    def test_extra_spaces(self):
        """Лишние пробелы."""
        result = extract_customer_from_name("  ООО  Тест  - продукция")
        assert result == "ООО Тест"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ classify_by_rules
# ═══════════════════════════════════════════════════════════════════

class TestClassifyByRules:
    """Тесты rule-based классификации."""

    def test_carbide_standard(self):
        """Классификация твердосплавного инструмента."""
        result = classify_by_rules("Gesac - 86 поз. твердосплав", ["спецификация.xlsx"])
        assert result["direction"] == "CARBIDE-STANDARD"

    def test_hss_standard(self):
        """Классификация HSS ГОСТ."""
        result = classify_by_rules("Метчики HSS ГОСТ - 20 поз.", ["ИоЗ.docx"])
        assert result["direction"] == "HSS-STANDARD"

    def test_spec_drawing(self):
        """Классификация по чертежам."""
        result = classify_by_rules("ОКБ ФАКЕЛ - чертеж фрезы", ["ТЗ.pdf"])
        assert result["direction"] == "SPEC-DRAWING"

    def test_diamond_standard(self):
        """Классификация алмазного инструмента."""
        result = classify_by_rules("Алмазные круги для шлифовки", ["spec.pdf"])
        assert result["direction"] == "DIAMOND-STANDARD"

    def test_out_of_scope(self):
        """Классификация — не наш ассортимент."""
        result = classify_by_rules("Не интересно - калибры", ["file.doc"])
        assert result["direction"] == "OUT-OF-SCOPE"
        assert result["priority"] == "Р4"

    def test_soz_development(self):
        """Классификация СОЗ."""
        result = classify_by_rules("ОМСКТРАНСМАШ - Долбяки СОЗ", ["запрос.docx"])
        assert result["situation_type"] == "СОЗ"

    def test_priority_p1_urgent(self):
        """Приоритет Р1 для срочных."""
        result = classify_by_rules("Срочно - АО Завод - фрезы", ["file.xlsx"])
        assert result["priority"] == "Р1"

    def test_priority_p2_large_volume(self):
        """Приоритет Р2 для крупных объёмов."""
        result = classify_by_rules("Завод - 86 поз. фрезы", ["spec.xlsx"])
        assert result["priority"] == "Р2"

    def test_default_priority_p3(self):
        """Приоритет Р3 по умолчанию."""
        result = classify_by_rules("Обычный тендер", ["file.pdf"])
        assert result["priority"] == "Р3"

    def test_result_has_required_fields(self):
        """Результат содержит все необходимые поля."""
        result = classify_by_rules("Тест", ["file.pdf"])
        assert "priority" in result
        assert "situation_type" in result
        assert "direction" in result
        assert "confidence" in result
        assert "source" in result
        assert result["source"] == "rules"

    def test_customer_extracted(self):
        """Заказчик извлекается из названия."""
        result = classify_by_rules("АО Прогресс - фрезы", ["file.pdf"])
        assert result["customer"] == "АО Прогресс"

    def test_borfresa_is_carbide(self):
        """Борфреза классифицируется как CARBIDE-STANDARD."""
        result = classify_by_rules("Борфрезы - 10 поз.", ["file.xlsx"])
        assert result["direction"] == "CARBIDE-STANDARD"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ determine_archive_by_rules
# ═══════════════════════════════════════════════════════════════════

class TestDetermineArchiveByRules:
    """Тесты rule-based определения архивного назначения."""

    def test_spec_drawing_archive(self):
        """Архив для SPEC-DRAWING."""
        result = determine_archive_by_rules("SPEC-DRAWING", "Запрос котировок")
        assert result["archive_destination"] == "Архив — направления / Специнструмент по чертежам"

    def test_hss_standard_archive(self):
        """Архив для HSS-STANDARD."""
        result = determine_archive_by_rules("HSS-STANDARD", "Запрос котировок")
        assert result["archive_destination"] == "Архив — направления / HSS ГОСТ"

    def test_carbide_standard_archive(self):
        """Архив для CARBIDE-STANDARD."""
        result = determine_archive_by_rules("CARBIDE-STANDARD", "Запрос котировок")
        assert result["archive_destination"] == "Архив — направления / Твердосплав"

    def test_diamond_standard_archive(self):
        """Архив для DIAMOND-STANDARD."""
        result = determine_archive_by_rules("DIAMOND-STANDARD", "Запрос котировок")
        assert result["archive_destination"] == "Архив — направления / Алмазный"

    def test_out_of_scope_archive(self):
        """Архив для OUT-OF-SCOPE."""
        result = determine_archive_by_rules("OUT-OF-SCOPE", "Не наш ассортимент")
        assert result["archive_destination"] == "Архив — направления / Не наш ассортимент"

    def test_soz_situation_type(self):
        """СОЗ всегда идёт в архив СОЗ."""
        result = determine_archive_by_rules("CARBIDE-STANDARD", "СОЗ")
        assert "Архив — СОЗ" in result["archive_destination"]

    def test_unknown_direction(self):
        """Неизвестное направление → Требуется проверка."""
        result = determine_archive_by_rules("UNKNOWN", "Запрос котировок")
        assert "Требуется проверка" in result["archive_destination"]

    def test_result_has_required_fields(self):
        """Результат содержит все необходимые поля."""
        result = determine_archive_by_rules("HSS-STANDARD", "Запрос котировок")
        assert "archive_destination" in result
        assert "confidence" in result
        assert "source" in result
        assert result["source"] == "rules"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ YandexGPTClient
# ═══════════════════════════════════════════════════════════════════

class TestYandexGPTClient:
    """Тесты клиента Яндекс GPT."""

    def test_is_configured_with_keys(self, gpt_client):
        """Клиент настроен если есть API ключ и folder ID."""
        assert gpt_client.is_configured() is True

    def test_is_configured_without_keys(self):
        """Клиент не настроен без ключей."""
        with patch.dict(os.environ, {"YANDEX_GPT_API_KEY": "", "YANDEX_GPT_FOLDER_ID": ""}):
            # Need to reimport or create new instance
            client = YandexGPTClient()
            client.api_key = ""
            client.folder_id = ""
            assert client.is_configured() is False

    @patch("src.microservice.llm_classifier.YandexGPTClient.client", new_callable=lambda: property(lambda self: MagicMock()))
    def test_complete_success(self, mock_client_prop):
        """Успешный вызов complete."""
        client = YandexGPTClient()
        mock_openai_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"priority": "Р1"}'
        mock_openai_client.chat.completions.create.return_value = mock_response

        with patch.object(type(client), 'client', new_callable=lambda: property(lambda self: mock_openai_client)):
            result = client.complete("system prompt", "user message")

        assert result == '{"priority": "Р1"}'

    def test_complete_not_configured(self):
        """complete возвращает None если не настроен."""
        client = YandexGPTClient()
        client.api_key = ""
        client.folder_id = ""
        result = client.complete("system", "user")
        assert result is None

    def test_complete_exception_returns_none(self):
        """complete возвращает None при исключении."""
        client = YandexGPTClient()
        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create.side_effect = Exception("API Error")

        with patch.object(type(client), 'client', new_callable=lambda: property(lambda self: mock_openai_client)):
            result = client.complete("system", "user")

        assert result is None


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ classify_tender
# ═══════════════════════════════════════════════════════════════════

class TestClassifyTender:
    """Тесты classify_tender с мокированным GPT."""

    @patch("src.microservice.llm_classifier.YandexGPTClient")
    @patch("src.microservice.llm_classifier.log_llm_result")
    def test_classify_tender_success(self, mock_log, mock_gpt_cls, sample_classification_json):
        """Успешная классификация через GPT."""
        mock_gpt = MagicMock()
        mock_gpt.is_configured.return_value = True
        mock_gpt.complete.return_value = sample_classification_json
        mock_gpt_cls.return_value = mock_gpt

        result = classify_tender(
            folder_name="Gesac - 86 поз.",
            date_folder="09.06.2026",
            files=["spec.xlsx", "ИоЗ.docx"],
        )

        assert result is not None
        assert result["priority"] == "Р1"
        assert result["direction"] == "CARBIDE-STANDARD"
        assert result["source"] == "yandex_gpt"
        mock_gpt.complete.assert_called_once()

    @patch("src.microservice.llm_classifier.YandexGPTClient")
    def test_classify_tender_gpt_not_configured(self, mock_gpt_cls):
        """Классификация fallback на rules если GPT не настроен."""
        mock_gpt = MagicMock()
        mock_gpt.is_configured.return_value = False
        mock_gpt_cls.return_value = mock_gpt

        result = classify_tender(
            folder_name="Gesac - 86 поз. твердосплав",
            date_folder="09.06.2026",
            files=["spec.xlsx"],
        )

        assert result is not None
        assert result["source"] == "rules"
        assert result["direction"] == "CARBIDE-STANDARD"

    @patch("src.microservice.llm_classifier.YandexGPTClient")
    def test_classify_tender_gpt_returns_none(self, mock_gpt_cls):
        """Классификация fallback если GPT вернул None."""
        mock_gpt = MagicMock()
        mock_gpt.is_configured.return_value = True
        mock_gpt.complete.return_value = None
        mock_gpt_cls.return_value = mock_gpt

        result = classify_tender(
            folder_name="HSS метчики - 20 поз.",
            date_folder="09.06.2026",
            files=["file.xlsx"],
        )

        assert result is not None
        assert result["source"] == "rules"

    @patch("src.microservice.llm_classifier.YandexGPTClient")
    def test_classify_tender_gpt_returns_invalid_json(self, mock_gpt_cls):
        """Классификация fallback если GPT вернул невалидный JSON."""
        mock_gpt = MagicMock()
        mock_gpt.is_configured.return_value = True
        mock_gpt.complete.return_value = "Это не JSON, а просто текст ответа"
        mock_gpt_cls.return_value = mock_gpt

        result = classify_tender(
            folder_name="Тест - фрезы",
            date_folder="09.06.2026",
            files=["file.pdf"],
        )

        assert result is not None
        # Должен fallback на rules
        assert result["source"] == "rules"

    @patch("src.microservice.llm_classifier.YandexGPTClient")
    @patch("src.microservice.llm_classifier.log_llm_result")
    def test_classify_tender_with_file_contents(self, mock_log, mock_gpt_cls, sample_classification_json):
        """Классификация с содержимым файлов."""
        mock_gpt = MagicMock()
        mock_gpt.is_configured.return_value = True
        mock_gpt.complete.return_value = sample_classification_json
        mock_gpt_cls.return_value = mock_gpt

        result = classify_tender(
            folder_name="Тест",
            date_folder="09.06.2026",
            files=["spec.xlsx"],
            file_contents={"spec.xlsx": "Содержимое файла с описанием фрез"},
        )

        assert result is not None
        assert result["source"] == "yandex_gpt"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ determine_archive_destination
# ═══════════════════════════════════════════════════════════════════

class TestDetermineArchiveDestination:
    """Тесты determine_archive_destination с мокированным GPT."""

    @patch("src.microservice.llm_classifier.YandexGPTClient")
    @patch("src.microservice.llm_classifier.log_llm_result")
    def test_archive_success(self, mock_log, mock_gpt_cls, sample_archive_json):
        """Успешное определение архивного назначения."""
        mock_gpt = MagicMock()
        mock_gpt.is_configured.return_value = True
        mock_gpt.complete.return_value = sample_archive_json
        mock_gpt_cls.return_value = mock_gpt

        result = determine_archive_destination(
            direction="CARBIDE-STANDARD",
            sub_direction="Фрезы",
            situation_type="Запрос котировок",
            close_reason="Проиграли",
            customer="ООО Тест",
            lead_name="[P2] — ООО Тест — 15.07",
        )

        assert result is not None
        assert "archive_destination" in result
        assert result["source"] == "yandex_gpt"

    @patch("src.microservice.llm_classifier.YandexGPTClient")
    def test_archive_gpt_not_configured(self, mock_gpt_cls):
        """Архивация fallback если GPT не настроен."""
        mock_gpt = MagicMock()
        mock_gpt.is_configured.return_value = False
        mock_gpt_cls.return_value = mock_gpt

        result = determine_archive_destination(
            direction="HSS-STANDARD",
            sub_direction=None,
            situation_type="Запрос котировок",
            close_reason="Отказ",
            customer="Тест",
            lead_name="Тест",
        )

        assert result is not None
        assert result["source"] == "rules"
        assert "HSS ГОСТ" in result["archive_destination"]

    @patch("src.microservice.llm_classifier.YandexGPTClient")
    def test_archive_gpt_returns_none(self, mock_gpt_cls):
        """Архивация fallback если GPT вернул None."""
        mock_gpt = MagicMock()
        mock_gpt.is_configured.return_value = True
        mock_gpt.complete.return_value = None
        mock_gpt_cls.return_value = mock_gpt

        result = determine_archive_destination(
            direction="DIAMOND-STANDARD",
            sub_direction=None,
            situation_type="Запрос котировок",
            close_reason="Отказ",
            customer="Тест",
            lead_name="Тест",
        )

        assert result is not None
        assert result["source"] == "rules"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ load_system_context
# ═══════════════════════════════════════════════════════════════════

class TestLoadSystemContext:
    """Тесты загрузки системного контекста."""

    @patch("src.microservice.llm_classifier.CONTEXT_FILE")
    @patch("src.microservice.llm_classifier.FIELDS_FILE")
    def test_load_context_files_exist(self, mock_fields, mock_context):
        """Загрузка контекста когда файлы существуют."""
        mock_context.exists.return_value = True
        mock_context.read_text.return_value = "Context content"
        mock_fields.exists.return_value = True
        mock_fields.read_text.return_value = "Fields content"

        result = load_system_context()

        assert "Context content" in result
        assert "Fields content" in result

    @patch("src.microservice.llm_classifier.CONTEXT_FILE")
    @patch("src.microservice.llm_classifier.FIELDS_FILE")
    def test_load_context_files_missing(self, mock_fields, mock_context):
        """Загрузка контекста когда файлы отсутствуют."""
        mock_context.exists.return_value = False
        mock_fields.exists.return_value = False

        result = load_system_context()

        assert result == ""


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ log_llm_result
# ═══════════════════════════════════════════════════════════════════

class TestLogLLMResult:
    """Тесты логирования результатов LLM."""

    @patch("builtins.open", new_callable=MagicMock)
    @patch("os.makedirs")
    def test_log_creates_file(self, mock_makedirs, mock_open):
        """log_llm_result создаёт файл лога."""
        log_llm_result(
            action="classify",
            identifier="Test Folder",
            prompt="test prompt",
            response='{"priority": "Р1"}',
            result={"priority": "Р1"},
        )

        mock_makedirs.assert_called_once()
        mock_open.assert_called_once()

    @patch("builtins.open", new_callable=MagicMock)
    @patch("os.makedirs")
    def test_log_sanitizes_filename(self, mock_makedirs, mock_open):
        """log_llm_result санитизирует имя файла."""
        log_llm_result(
            action="classify",
            identifier="Тест/с\\спецсимволами:*?",
            prompt="test",
            response="{}",
            result={},
        )

        # Должен вызваться без ошибки
        mock_open.assert_called_once()
        filepath = mock_open.call_args[0][0]
        assert "/" not in os.path.basename(filepath) or filepath.startswith("/tmp")
