"""
Быстрый тест валидации полей — без обращения к amoCRM API.
Тестирует логику определения обязательных полей по статусу.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from microservice.field_validator import (
    FieldValidator,
    ValidationResult,
    REQUIRED_FIELDS_BY_STATUS,
    FIELD_IDS,
    get_status_key_by_id,
)

print("=" * 60)
print("ТЕСТ ВАЛИДАЦИИ ПОЛЕЙ")
print("=" * 60)

# ─── Тест 1: Карта обязательных полей заполнена ──────────
print("\n--- Тест 1: Обязательные поля для каждого статуса ---")
for status_key, fields in REQUIRED_FIELDS_BY_STATUS.items():
    field_names = [f[1] for f in fields]
    print(f"  {status_key}: {field_names}")

assert len(REQUIRED_FIELDS_BY_STATUS) > 0, "Карта обязательных полей пуста!"
print(f"\n  ✅ {len(REQUIRED_FIELDS_BY_STATUS)} статусов с обязательными полями")

# ─── Тест 2: FIELD_IDS загружены ─────────────────────────
print("\n--- Тест 2: ID полей загружены ---")
for name, fid in FIELD_IDS.items():
    print(f"  {name}: {fid}")
assert all(v > 0 for v in FIELD_IDS.values()), "Некоторые ID полей = 0!"
print(f"\n  ✅ {len(FIELD_IDS)} полей с валидными ID")

# ─── Тест 3: get_status_key_by_id ────────────────────────
print("\n--- Тест 3: Маппинг status_id → status_key ---")
status_5_id = int(os.getenv("STATUS_5_PURCHASING", "86357390"))
key = get_status_key_by_id(status_5_id)
if key:
    print(f"  ID {status_5_id} → {key}")
    assert key == "STATUS_5_PURCHASING"
    print(f"  ✅ Маппинг работает")
else:
    print(f"  ⚠️ Статус {status_5_id} не найден в маппинге")

# ─── Тест 4: Формирование сообщения ──────────────────────
print("\n--- Тест 4: Формирование предупреждений ---")
validator = FieldValidator()

# Эмулируем результат с блокирующими полями
result = ValidationResult()
result.missing_block = ["Заказчик", "Направление"]
result.missing_warn = ["НМЦ"]
result.has_blockers = True
result.is_valid = False

message = validator._format_message(result, "STATUS_5_PURCHASING")
assert "🚫" in message
assert "Заказчик" in message
assert "НМЦ" in message
print(f"  ✅ Сообщение с блокировкой:")
for line in message.split("\n"):
    print(f"     {line}")

# ─── Тест 5: Результат без ошибок ────────────────────────
print("\n--- Тест 5: Все поля заполнены ---")
result_ok = ValidationResult()
message_ok = validator._format_message(result_ok, "STATUS_5_PURCHASING")
assert "✅" in message_ok
print(f"  ✅ Сообщение: {message_ok}")

# ─── Тест 6: Только предупреждения (без блокировки) ──────
print("\n--- Тест 6: Только предупреждения ---")
result_warn = ValidationResult()
result_warn.missing_warn = ["Дедлайн подачи", "Тип процедуры"]
result_warn.is_valid = True

message_warn = validator._format_message(result_warn, "STATUS_6_KP_PREP")
assert "⚠️" in message_warn
assert "🚫" not in message_warn
print(f"  ✅ Только предупреждения (не блокирует):")
for line in message_warn.split("\n"):
    print(f"     {line}")

# ─── Тест 7: Архивирование — строгие правила ─────────────
print("\n--- Тест 7: Правила архивирования ---")
archive_rules = REQUIRED_FIELDS_BY_STATUS.get("STATUS_11_ARCHIVE", [])
block_fields = [f[1] for f in archive_rules if f[2] == "block"]
warn_fields = [f[1] for f in archive_rules if f[2] == "warn"]
print(f"  Блокирующие: {block_fields}")
print(f"  Предупреждения: {warn_fields}")
assert "Причина закрытия" in block_fields
assert "Архивное назначение итоговое" in block_fields
print(f"  ✅ Архивирование блокируется без причины и назначения")

# ─── Тест 8: Торги — обязательные поля ───────────────────
print("\n--- Тест 8: Правила для Торгов ---")
bidding_rules = REQUIRED_FIELDS_BY_STATUS.get("STATUS_9_BIDDING", [])
bidding_block = [f[1] for f in bidding_rules if f[2] == "block"]
bidding_warn = [f[1] for f in bidding_rules if f[2] == "warn"]
print(f"  Блокирующие: {bidding_block}")
print(f"  Предупреждения: {bidding_warn}")
assert "Заказчик" in bidding_block
assert "НМЦ" in bidding_block
print(f"  ✅ Торги блокируются без заказчика и НМЦ")

print("\n" + "=" * 60)
print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ ✅")
print("=" * 60)
