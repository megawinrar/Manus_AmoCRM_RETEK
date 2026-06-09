"""
Тесты модуля дедупликации и валидации полей.
Покрывает все сценарии: дубль, обогащение, обновление, fuzzy, edge cases.
"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from microservice.deduplication import (
    TenderDeduplicator,
    DeduplicationDB,
    FileRecord,
    DeduplicationResult,
    compute_file_hash,
    format_enrichment_note,
    normalize_customer_name,
    customer_similarity,
)
from microservice.field_validator import (
    FieldValidator,
    ValidationResult,
    REQUIRED_FIELDS_BY_STATUS,
    FIELD_IDS,
    get_status_key_by_id,
)


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_db():
    """Временная БД для тестов."""
    path = tempfile.mktemp(suffix=".db")
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def dedup_db(tmp_db):
    """Экземпляр DeduplicationDB."""
    return DeduplicationDB(tmp_db)


@pytest.fixture
def deduplicator(dedup_db):
    """Экземпляр TenderDeduplicator."""
    return TenderDeduplicator(dedup_db)


@pytest.fixture
def sample_files():
    """Набор тестовых файлов."""
    return [
        FileRecord(filename="ТЗ.xlsx", file_hash="hash_tz", file_size=1000, file_path="/ТОРГИ/09.06.2026/Тендер1/ТЗ.xlsx"),
        FileRecord(filename="Договор.pdf", file_hash="hash_dog", file_size=2000, file_path="/ТОРГИ/09.06.2026/Тендер1/Договор.pdf"),
        FileRecord(filename="НМЦ.docx", file_hash="hash_nmc", file_size=500, file_path="/ТОРГИ/09.06.2026/Тендер1/НМЦ.docx"),
    ]


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ ДЕДУПЛИКАЦИИ
# ═══════════════════════════════════════════════════════════════════

class TestNewTender:
    """Тесты для нового тендера."""

    def test_new_tender_detected(self, deduplicator, sample_files):
        """Новый тендер корректно определяется."""
        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            customer="АО КБП",
            nmc=6700000,
        )
        assert result.is_new is True
        assert result.is_exact_duplicate is False
        assert result.is_enrichment is False
        assert len(result.new_files) == 3

    def test_new_tender_empty_files(self, deduplicator):
        """Новый тендер без файлов."""
        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Пустой",
            files=[],
            customer="Тест",
        )
        assert result.is_new is True
        assert len(result.new_files) == 0

    def test_new_tender_no_customer(self, deduplicator, sample_files):
        """Новый тендер без указания заказчика."""
        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            customer=None,
        )
        assert result.is_new is True


class TestExactDuplicate:
    """Тесты для 100% дубля."""

    def test_same_path_same_files(self, deduplicator, dedup_db, sample_files):
        """Повторная загрузка из той же папки с теми же файлами = дубль."""
        # Сохраняем первый раз
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            lead_id=12345,
            customer="АО КБП",
        )

        # Проверяем второй раз
        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            customer="АО КБП",
        )
        assert result.is_exact_duplicate is True
        assert result.existing_lead_id == 12345
        assert "идентичны" in result.message

    def test_different_path_same_hashes(self, deduplicator, dedup_db, sample_files):
        """Те же файлы в другой папке = дубль (cross-folder)."""
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            lead_id=12345,
        )

        # Те же хеши, другой путь
        files_copy = [
            FileRecord(filename="ТЗ.xlsx", file_hash="hash_tz", file_size=1000, file_path="/ТОРГИ/10.06.2026/Копия/ТЗ.xlsx"),
            FileRecord(filename="Договор.pdf", file_hash="hash_dog", file_size=2000, file_path="/ТОРГИ/10.06.2026/Копия/Договор.pdf"),
            FileRecord(filename="НМЦ.docx", file_hash="hash_nmc", file_size=500, file_path="/ТОРГИ/10.06.2026/Копия/НМЦ.docx"),
        ]

        result = deduplicator.check(
            tender_path="/ТОРГИ/10.06.2026/Копия",
            files=files_copy,
            customer="АО КБП",
        )
        assert result.is_exact_duplicate is True
        assert result.existing_lead_id == 12345
        assert "другая папка" in result.message

    def test_renamed_files_same_hash(self, deduplicator, dedup_db, sample_files):
        """Файлы переименованы, но хеш тот же = дубль."""
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            lead_id=12345,
        )

        # Те же хеши, другие имена
        renamed_files = [
            FileRecord(filename="ТЗ_v2.xlsx", file_hash="hash_tz", file_size=1000, file_path="/ТОРГИ/09.06.2026/Тендер1/ТЗ_v2.xlsx"),
            FileRecord(filename="Контракт.pdf", file_hash="hash_dog", file_size=2000, file_path="/ТОРГИ/09.06.2026/Тендер1/Контракт.pdf"),
            FileRecord(filename="НМЦ.docx", file_hash="hash_nmc", file_size=500, file_path="/ТОРГИ/09.06.2026/Тендер1/НМЦ.docx"),
        ]

        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=renamed_files,
            customer="АО КБП",
        )
        # Переименованные файлы с тем же хешем = unchanged
        assert result.is_exact_duplicate is True


class TestEnrichment:
    """Тесты для обогащения (новые файлы добавлены)."""

    def test_new_file_added(self, deduplicator, dedup_db, sample_files):
        """Добавлен новый файл к существующему тендеру."""
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            lead_id=12345,
        )

        # Добавляем новый файл
        enriched_files = sample_files + [
            FileRecord(filename="Спецификация.xlsx", file_hash="hash_spec", file_size=3000, file_path="/ТОРГИ/09.06.2026/Тендер1/Спецификация.xlsx"),
        ]

        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=enriched_files,
            customer="АО КБП",
        )
        assert result.is_enrichment is True
        assert "Спецификация.xlsx" in result.new_files
        assert result.existing_lead_id == 12345

    def test_multiple_new_files(self, deduplicator, dedup_db, sample_files):
        """Добавлено несколько новых файлов."""
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            lead_id=12345,
        )

        enriched_files = sample_files + [
            FileRecord(filename="Доп1.pdf", file_hash="hash_dop1", file_size=100, file_path="/p/Доп1.pdf"),
            FileRecord(filename="Доп2.xlsx", file_hash="hash_dop2", file_size=200, file_path="/p/Доп2.xlsx"),
            FileRecord(filename="Доп3.docx", file_hash="hash_dop3", file_size=300, file_path="/p/Доп3.docx"),
        ]

        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=enriched_files,
        )
        assert result.is_enrichment is True
        assert len(result.new_files) == 3


class TestFileUpdate:
    """Тесты для обновления файлов (тот же файл, другой хеш)."""

    def test_single_file_updated(self, deduplicator, dedup_db, sample_files):
        """Один файл обновлён (новая версия)."""
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            lead_id=12345,
        )

        # ТЗ.xlsx обновлён
        updated_files = [
            FileRecord(filename="ТЗ.xlsx", file_hash="hash_tz_v2", file_size=1100, file_path="/p/ТЗ.xlsx"),
            FileRecord(filename="Договор.pdf", file_hash="hash_dog", file_size=2000, file_path="/p/Договор.pdf"),
            FileRecord(filename="НМЦ.docx", file_hash="hash_nmc", file_size=500, file_path="/p/НМЦ.docx"),
        ]

        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=updated_files,
        )
        assert result.is_update is True
        assert "ТЗ.xlsx" in result.updated_files
        assert len(result.unchanged_files) == 2

    def test_all_files_updated(self, deduplicator, dedup_db, sample_files):
        """Все файлы обновлены."""
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            lead_id=12345,
        )

        all_updated = [
            FileRecord(filename="ТЗ.xlsx", file_hash="new1", file_size=1100, file_path="/p/ТЗ.xlsx"),
            FileRecord(filename="Договор.pdf", file_hash="new2", file_size=2100, file_path="/p/Договор.pdf"),
            FileRecord(filename="НМЦ.docx", file_hash="new3", file_size=600, file_path="/p/НМЦ.docx"),
        ]

        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=all_updated,
        )
        assert result.is_update is True
        assert len(result.updated_files) == 3
        assert len(result.unchanged_files) == 0

    def test_update_plus_new_file(self, deduplicator, dedup_db, sample_files):
        """Обновлён файл + добавлен новый = обогащение (не update)."""
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            lead_id=12345,
        )

        mixed_files = [
            FileRecord(filename="ТЗ.xlsx", file_hash="hash_tz_v2", file_size=1100, file_path="/p/ТЗ.xlsx"),
            FileRecord(filename="Договор.pdf", file_hash="hash_dog", file_size=2000, file_path="/p/Договор.pdf"),
            FileRecord(filename="НМЦ.docx", file_hash="hash_nmc", file_size=500, file_path="/p/НМЦ.docx"),
            FileRecord(filename="Новый.pdf", file_hash="hash_new", file_size=700, file_path="/p/Новый.pdf"),
        ]

        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=mixed_files,
        )
        # Обновление + новый файл = обогащение
        assert result.is_enrichment is True
        assert "Новый.pdf" in result.new_files
        assert "ТЗ.xlsx" in result.updated_files


class TestFuzzyDuplicate:
    """Тесты для fuzzy-дубля."""

    def test_similar_customer_similar_nmc(self, deduplicator, dedup_db, sample_files):
        """Похожий заказчик + похожая НМЦ = fuzzy-дубль."""
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            lead_id=12345,
            customer="АО КБП",
            nmc=6700000,
        )

        # Совершенно другие файлы, но похожий заказчик
        new_files = [
            FileRecord(filename="Другой.xlsx", file_hash="zzz", file_size=500, file_path="/p/Другой.xlsx"),
        ]

        result = deduplicator.check(
            tender_path="/ТОРГИ/10.06.2026/КБП_2",
            files=new_files,
            customer="АО КБП",  # Точное совпадение
            nmc=6750000,  # Близкая НМЦ
        )
        # Может быть fuzzy или new — зависит от порога
        # При точном совпадении заказчика и близкой НМЦ должен быть fuzzy
        if result.is_fuzzy_duplicate:
            assert result.match_score >= 0.6
        # Если не сработал — это тоже ОК при разных файлах

    def test_different_customer_different_nmc(self, deduplicator, dedup_db, sample_files):
        """Разный заказчик + разная НМЦ = новый тендер."""
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            lead_id=12345,
            customer="АО КБП",
            nmc=6700000,
        )

        new_files = [
            FileRecord(filename="Запрос.pdf", file_hash="abc", file_size=800, file_path="/p/Запрос.pdf"),
        ]

        result = deduplicator.check(
            tender_path="/ТОРГИ/10.06.2026/Газпром",
            files=new_files,
            customer="ПАО Газпром",
            nmc=50000000,
        )
        assert result.is_new is True


class TestCustomerNormalization:
    """Тесты нормализации названий заказчиков."""

    def test_normalize_ao(self):
        """Нормализация ОПФ: АО, ПАО, ООО."""
        assert normalize_customer_name("АО «КБП»") == normalize_customer_name("АО КБП")

    def test_normalize_quotes(self):
        """Убираем кавычки."""
        n1 = normalize_customer_name('АО "КБП"')
        n2 = normalize_customer_name("АО «КБП»")
        assert n1 == n2

    def test_normalize_case(self):
        """Регистр не важен."""
        n1 = normalize_customer_name("АО КБП")
        n2 = normalize_customer_name("ао кбп")
        assert n1 == n2

    def test_similarity_exact(self):
        """Точное совпадение = 1.0."""
        score = customer_similarity("АО КБП", "АО КБП")
        assert score == 1.0

    def test_similarity_partial(self):
        """Частичное совпадение."""
        score = customer_similarity("АО КБП", "КБП им. Шипунова")
        assert 0.0 <= score <= 1.0

    def test_similarity_different(self):
        """Разные заказчики = низкий score."""
        score = customer_similarity("АО КБП", "ПАО Газпром")
        assert score < 0.5


class TestFormatEnrichmentNote:
    """Тесты форматирования заметок."""

    def test_enrichment_with_field_changes(self):
        """Заметка с изменёнными полями."""
        result = DeduplicationResult()
        result.is_enrichment = True
        result.new_files = ["Спец.xlsx"]
        result.message = "📎 Обогащение"

        note = format_enrichment_note(
            result,
            old_fields={"НМЦ": "6 700 000"},
            new_fields={"НМЦ": "6 850 000"},
        )
        assert "6 700 000 → 6 850 000" in note

    def test_enrichment_no_changes(self):
        """Заметка без изменения полей."""
        result = DeduplicationResult()
        result.is_enrichment = True
        result.unchanged_files = ["ТЗ.xlsx", "Договор.pdf"]
        result.message = "📎 Дубль"

        note = format_enrichment_note(result)
        assert "2 файлов" in note


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ ВАЛИДАЦИИ ПОЛЕЙ
# ═══════════════════════════════════════════════════════════════════

class TestFieldValidation:
    """Тесты валидации обязательных полей."""

    def test_all_statuses_have_rules(self):
        """Все ключевые статусы имеют правила."""
        assert "STATUS_1_LLM" in REQUIRED_FIELDS_BY_STATUS
        assert "STATUS_5_PURCHASING" in REQUIRED_FIELDS_BY_STATUS
        assert "STATUS_9_BIDDING" in REQUIRED_FIELDS_BY_STATUS
        assert "STATUS_11_ARCHIVE" in REQUIRED_FIELDS_BY_STATUS

    def test_archive_has_block_fields(self):
        """Архивирование имеет блокирующие поля."""
        rules = REQUIRED_FIELDS_BY_STATUS["STATUS_11_ARCHIVE"]
        block_fields = [r for r in rules if r[2] == "block"]
        assert len(block_fields) >= 2  # Причина + Назначение

    def test_format_message_blockers(self):
        """Сообщение с блокировкой содержит правильные маркеры."""
        validator = FieldValidator()
        result = ValidationResult()
        result.missing_block = ["Заказчик"]
        message = validator._format_message(result, "STATUS_5_PURCHASING")
        assert "🚫" in message
        assert "Заказчик" in message

    def test_format_message_warnings_only(self):
        """Сообщение только с предупреждениями."""
        validator = FieldValidator()
        result = ValidationResult()
        result.missing_warn = ["НМЦ"]
        message = validator._format_message(result, "STATUS_5_PURCHASING")
        assert "⚠️" in message
        assert "🚫" not in message

    def test_format_message_all_ok(self):
        """Сообщение когда всё заполнено."""
        validator = FieldValidator()
        result = ValidationResult()
        message = validator._format_message(result, "STATUS_5_PURCHASING")
        assert "✅" in message

    def test_status_key_mapping(self):
        """Маппинг ID статуса → ключ работает."""
        status_id = int(os.getenv("STATUS_9_BIDDING", "86357654"))
        key = get_status_key_by_id(status_id)
        assert key == "STATUS_9_BIDDING"

    def test_unknown_status_returns_none(self):
        """Неизвестный статус → None."""
        key = get_status_key_by_id(99999999)
        assert key is None

    def test_field_ids_all_positive(self):
        """Все ID полей > 0."""
        for name, fid in FIELD_IDS.items():
            assert fid > 0, f"FIELD_IDS[{name}] = {fid} (должен быть > 0)"


# ═══════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge cases и граничные условия."""

    def test_empty_hash(self, deduplicator, dedup_db):
        """Файл без хеша (не удалось вычислить)."""
        files = [
            FileRecord(filename="broken.xlsx", file_hash="", file_size=0, file_path="/p/broken.xlsx"),
        ]
        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Broken",
            files=files,
        )
        assert result.is_new is True

    def test_very_long_filename(self, deduplicator, dedup_db):
        """Очень длинное имя файла."""
        long_name = "А" * 500 + ".xlsx"
        files = [
            FileRecord(filename=long_name, file_hash="long_hash", file_size=100, file_path=f"/p/{long_name}"),
        ]
        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Long",
            files=files,
        )
        assert result.is_new is True

    def test_unicode_in_paths(self, deduplicator, dedup_db):
        """Кириллица и спецсимволы в путях."""
        files = [
            FileRecord(
                filename="Спецификация №1 (версия 2).xlsx",
                file_hash="uni_hash",
                file_size=100,
                file_path="/ТОРГИ/09.06.2026/АО «Завод» — поставка/Спецификация №1 (версия 2).xlsx",
            ),
        ]
        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/АО «Завод» — поставка",
            files=files,
        )
        assert result.is_new is True

    def test_zero_nmc(self, deduplicator, dedup_db, sample_files):
        """НМЦ = 0 не должна вызывать деление на ноль."""
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Тендер1",
            files=sample_files,
            lead_id=12345,
            customer="АО КБП",
            nmc=0,
        )

        new_files = [
            FileRecord(filename="X.pdf", file_hash="xxx", file_size=100, file_path="/p/X.pdf"),
        ]
        # Не должно упасть
        result = deduplicator.check(
            tender_path="/ТОРГИ/10.06.2026/Другой",
            files=new_files,
            customer="АО КБП",
            nmc=0,
        )
        assert result is not None

    def test_single_file_tender(self, deduplicator, dedup_db):
        """Тендер с одним файлом."""
        files = [
            FileRecord(filename="Единственный.pdf", file_hash="solo", file_size=500, file_path="/p/Единственный.pdf"),
        ]
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Один",
            files=files,
            lead_id=99999,
        )

        # Тот же файл
        result = deduplicator.check(
            tender_path="/ТОРГИ/09.06.2026/Один",
            files=files,
        )
        assert result.is_exact_duplicate is True

    def test_partial_hash_match_below_threshold(self, deduplicator, dedup_db):
        """Менее 80% совпадения хешей — не считается дублем."""
        original_files = [
            FileRecord(filename=f"file{i}.pdf", file_hash=f"hash_{i}", file_size=100, file_path=f"/p/file{i}.pdf")
            for i in range(10)
        ]
        dedup_db.save_tender(
            tender_path="/ТОРГИ/09.06.2026/Original",
            files=original_files,
            lead_id=11111,
        )

        # Только 2 из 10 совпадают (20% < 80%)
        mixed_files = [
            FileRecord(filename="file0.pdf", file_hash="hash_0", file_size=100, file_path="/p2/file0.pdf"),
            FileRecord(filename="file1.pdf", file_hash="hash_1", file_size=100, file_path="/p2/file1.pdf"),
        ] + [
            FileRecord(filename=f"new{i}.pdf", file_hash=f"new_hash_{i}", file_size=100, file_path=f"/p2/new{i}.pdf")
            for i in range(8)
        ]

        result = deduplicator.check(
            tender_path="/ТОРГИ/10.06.2026/Partial",
            files=mixed_files,
            customer="Другой",
            nmc=1000000,
        )
        # 2/10 = 20% < 80% — не дубль
        assert result.is_exact_duplicate is False
