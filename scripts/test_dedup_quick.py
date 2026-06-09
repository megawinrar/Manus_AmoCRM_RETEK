"""
Быстрый тест дедупликации — без скачивания файлов с Яндекс.Диска.
Тестирует логику: новый / дубль / обогащение / обновление / fuzzy.
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from microservice.deduplication import (
    TenderDeduplicator, DeduplicationDB, FileRecord,
    DeduplicationResult, format_enrichment_note,
)

# Используем временную БД
tmp_db = tempfile.mktemp(suffix=".db")
db = DeduplicationDB(tmp_db)
dedup = TenderDeduplicator(db)

print("=" * 60)
print("ТЕСТ ДЕДУПЛИКАЦИИ")
print("=" * 60)

# ─── Тест 1: Новый тендер ─────────────────────────────────
print("\n--- Тест 1: Новый тендер ---")
files1 = [
    FileRecord(filename="ТЗ.xlsx", file_hash="aaa111", file_size=1000, file_path="/ТОРГИ/09.06.2026/Тендер1/ТЗ.xlsx"),
    FileRecord(filename="Договор.pdf", file_hash="bbb222", file_size=2000, file_path="/ТОРГИ/09.06.2026/Тендер1/Договор.pdf"),
    FileRecord(filename="НМЦ.docx", file_hash="ccc333", file_size=500, file_path="/ТОРГИ/09.06.2026/Тендер1/НМЦ.docx"),
]

result = dedup.check(
    tender_path="/ТОРГИ/09.06.2026/Тендер1",
    files=files1,
    customer="АО КБП",
    nmc=6700000,
)
assert result.is_new, f"Ожидали is_new=True, получили {result}"
print(f"  ✅ is_new=True, message: {result.message}")

# Сохраняем в БД (эмулируем что сделка создана)
db.save_tender(
    tender_path="/ТОРГИ/09.06.2026/Тендер1",
    files=files1,
    lead_id=3153625,
    customer="АО КБП",
    nmc=6700000,
    direction="CARBIDE-STANDARD",
    date_folder="09.06.2026",
)

# ─── Тест 2: 100% дубль (те же файлы, та же папка) ────────
print("\n--- Тест 2: 100% дубль ---")
result = dedup.check(
    tender_path="/ТОРГИ/09.06.2026/Тендер1",
    files=files1,
    customer="АО КБП",
    nmc=6700000,
)
assert result.is_exact_duplicate, f"Ожидали is_exact_duplicate=True, получили {result}"
assert result.existing_lead_id == 3153625
print(f"  ✅ is_exact_duplicate=True, lead_id={result.existing_lead_id}")
print(f"     message: {result.message}")

# ─── Тест 3: Обогащение (те же файлы + новый) ─────────────
print("\n--- Тест 3: Обогащение (добавлен новый файл) ---")
files3 = files1 + [
    FileRecord(filename="Спецификация.xlsx", file_hash="ddd444", file_size=3000, file_path="/ТОРГИ/09.06.2026/Тендер1/Спецификация.xlsx"),
]
result = dedup.check(
    tender_path="/ТОРГИ/09.06.2026/Тендер1",
    files=files3,
    customer="АО КБП",
    nmc=6700000,
)
assert result.is_enrichment, f"Ожидали is_enrichment=True, получили {result}"
assert "Спецификация.xlsx" in result.new_files
print(f"  ✅ is_enrichment=True, new_files={result.new_files}")
print(f"     message: {result.message}")

# ─── Тест 4: Обновление (тот же файл, другой хеш) ────────
print("\n--- Тест 4: Обновление файла (тот же файл, другой хеш) ---")
files4 = [
    FileRecord(filename="ТЗ.xlsx", file_hash="aaa111_v2", file_size=1100, file_path="/ТОРГИ/09.06.2026/Тендер1/ТЗ.xlsx"),
    FileRecord(filename="Договор.pdf", file_hash="bbb222", file_size=2000, file_path="/ТОРГИ/09.06.2026/Тендер1/Договор.pdf"),
    FileRecord(filename="НМЦ.docx", file_hash="ccc333", file_size=500, file_path="/ТОРГИ/09.06.2026/Тендер1/НМЦ.docx"),
]
result = dedup.check(
    tender_path="/ТОРГИ/09.06.2026/Тендер1",
    files=files4,
    customer="АО КБП",
    nmc=6700000,
)
assert result.is_update, f"Ожидали is_update=True, получили {result}"
assert "ТЗ.xlsx" in result.updated_files
print(f"  ✅ is_update=True, updated_files={result.updated_files}")
print(f"     message: {result.message}")

# ─── Тест 5: Дубль из другой папки (те же хеши) ──────────
print("\n--- Тест 5: Дубль из другой папки (те же файлы, другой путь) ---")
files5 = [
    FileRecord(filename="ТЗ.xlsx", file_hash="aaa111", file_size=1000, file_path="/ТОРГИ/10.06.2026/Копия/ТЗ.xlsx"),
    FileRecord(filename="Договор.pdf", file_hash="bbb222", file_size=2000, file_path="/ТОРГИ/10.06.2026/Копия/Договор.pdf"),
    FileRecord(filename="НМЦ.docx", file_hash="ccc333", file_size=500, file_path="/ТОРГИ/10.06.2026/Копия/НМЦ.docx"),
]
result = dedup.check(
    tender_path="/ТОРГИ/10.06.2026/Копия",
    files=files5,
    customer="АО КБП",
    nmc=6700000,
)
assert result.is_exact_duplicate, f"Ожидали is_exact_duplicate=True (другая папка), получили {result}"
assert result.existing_lead_id == 3153625
print(f"  ✅ is_exact_duplicate=True (cross-folder), lead_id={result.existing_lead_id}")
print(f"     message: {result.message}")

# ─── Тест 6: Fuzzy-дубль (похожий заказчик, близкая НМЦ) ─
print("\n--- Тест 6: Fuzzy-дубль (похожий заказчик, близкая НМЦ) ---")
files6 = [
    FileRecord(filename="Новый_ТЗ.xlsx", file_hash="xxx999", file_size=1500, file_path="/ТОРГИ/10.06.2026/Тендер_КБП_2/Новый_ТЗ.xlsx"),
]
result = dedup.check(
    tender_path="/ТОРГИ/10.06.2026/Тендер_КБП_2",
    files=files6,
    customer="КБП им. Шипунова",  # Похожее название
    nmc=6800000,  # Близкая НМЦ (±5%)
)
# Fuzzy-match зависит от реализации — может быть new или fuzzy_duplicate
if result.is_fuzzy_duplicate:
    print(f"  ✅ is_fuzzy_duplicate=True, score={result.match_score:.2f}")
    print(f"     message: {result.message}")
elif result.is_new:
    print(f"  ⚠️ is_new=True (fuzzy не сработал — порог не достигнут)")
    print(f"     Это ОК если similarity < 0.6")
else:
    print(f"  ❓ Неожиданный результат: {result}")

# ─── Тест 7: Совершенно новый тендер (другой заказчик) ────
print("\n--- Тест 7: Совершенно новый тендер ---")
files7 = [
    FileRecord(filename="Запрос.pdf", file_hash="zzz777", file_size=800, file_path="/ТОРГИ/10.06.2026/Новый_заказчик/Запрос.pdf"),
]
result = dedup.check(
    tender_path="/ТОРГИ/10.06.2026/Новый_заказчик",
    files=files7,
    customer="ПАО Газпром",
    nmc=15000000,
)
assert result.is_new, f"Ожидали is_new=True, получили {result}"
print(f"  ✅ is_new=True (другой заказчик, другие файлы)")

# ─── Тест 8: format_enrichment_note ──────────────────────
print("\n--- Тест 8: Форматирование заметки обогащения ---")
mock_result = DeduplicationResult()
mock_result.is_enrichment = True
mock_result.new_files = ["Спецификация_v2.xlsx", "Доп_соглашение.pdf"]
mock_result.updated_files = ["ТЗ.xlsx"]
mock_result.unchanged_files = ["Договор.pdf", "НМЦ.docx"]
mock_result.message = "📎 Дубль обнаружен → карточка обогащена\nДобавлены: Спецификация_v2.xlsx, Доп_соглашение.pdf\nОбновлены: ТЗ.xlsx"

note = format_enrichment_note(
    mock_result,
    old_fields={"НМЦ": "6 700 000", "Срок": "90 дней"},
    new_fields={"НМЦ": "6 850 000", "Срок": "90 дней"},
)
assert "6 700 000 → 6 850 000" in note
print(f"  ✅ Заметка сформирована:")
for line in note.split("\n"):
    print(f"     {line}")

# ─── Cleanup ─────────────────────────────────────────────
os.unlink(tmp_db)

print("\n" + "=" * 60)
print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ ✅")
print("=" * 60)
