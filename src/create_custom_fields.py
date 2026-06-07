"""
Создание 33 кастомных полей сделки в amoCRM по PATCH5 ТЗ.

Использование:
    python3 src/create_custom_fields.py --dry-run   # показать план (без запросов)
    python3 src/create_custom_fields.py --apply     # создать поля в amoCRM

Типы полей amoCRM:
    text        — текстовое поле
    numeric     — числовое
    select      — список (enum)
    multiselect — мультисписок
    date        — дата
    url         — ссылка
    textarea    — многострочный текст
    checkbox    — чекбокс (да/нет)
"""
import requests
import os
import sys
import time
import json
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("AMO_ACCESS_TOKEN")
BASE = os.getenv("AMO_BASE_DOMAIN", "tokutools.amocrm.ru")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
RATE_LIMIT_PAUSE = 1.5

DRY_RUN = "--dry-run" in sys.argv
APPLY = "--apply" in sys.argv

# === 33 КАСТОМНЫХ ПОЛЯ ПО PATCH5 ТЗ ===

CUSTOM_FIELDS = [
    # --- Идентификация ---
    {
        "name": "Внешний ID заявки",
        "type": "text",
        "group_id": "identification",
    },
    {
        "name": "Источник",
        "type": "select",
        "enums": [
            {"value": "Тендерная площадка"},
            {"value": "Прямой запрос"},
            {"value": "Email"},
            {"value": "Телефон"},
            {"value": "Другое"},
        ],
    },
    {
        "name": "Ссылка на площадку",
        "type": "url",
    },
    {
        "name": "Ссылка на папку / документы",
        "type": "url",
    },
    # --- Заказчик ---
    {
        "name": "Заказчик",
        "type": "text",
    },
    {
        "name": "ИНН",
        "type": "text",
    },
    {
        "name": "Номер процедуры",
        "type": "text",
    },
    # --- Классификация ---
    {
        "name": "Тип ситуации",
        "type": "select",
        "enums": [
            {"value": "СОЗ"},
            {"value": "Запрос котировок / реальные торги"},
            {"value": "Неясно"},
            {"value": "Не наш ассортимент"},
        ],
    },
    {
        "name": "Тип процедуры",
        "type": "select",
        "enums": [
            {"value": "Запрос котировок"},
            {"value": "Аукцион"},
            {"value": "Конкурс"},
            {"value": "Закупка у единственного поставщика"},
            {"value": "Другое"},
        ],
    },
    {
        "name": "Приоритет",
        "type": "select",
        "enums": [
            {"value": "Р1 — Срочно"},
            {"value": "Р2 — Быстрые Деньги"},
            {"value": "Р3 — Средние Деньги"},
            {"value": "Р4 — Наблюдаем / В базу"},
        ],
    },
    {
        "name": "Направление",
        "type": "select",
        "enums": [
            {"value": "SPEC-DRAWING — специнструмент по чертежам / ТЗ"},
            {"value": "HSS-STANDARD — стандартный быстрорез / ГОСТ"},
            {"value": "CARBIDE-STANDARD — стандартный твердосплав"},
            {"value": "DIAMOND-STANDARD — алмазный инструмент стандартный"},
            {"value": "SOZ-DEVELOPMENT — СОЗ / развитие / будущий торг"},
            {"value": "REAL-TENDER — реальные торги / запрос котировок"},
            {"value": "OUT-OF-SCOPE — не наш ассортимент"},
            {"value": "ARCHIVE-LEAD — база / наблюдение / будущая проработка"},
        ],
    },
    {
        "name": "Подтип направления",
        "type": "select",
        "enums": [
            {"value": "твердосплав по чертежам"},
            {"value": "быстрорез по чертежам"},
            {"value": "алмазный по чертежам"},
            {"value": "прочий инструмент по ТЗ"},
            {"value": "инструмент по эскизу / образцу"},
        ],
    },
    # --- Финансы и сроки ---
    {
        "name": "НМЦ",
        "type": "numeric",
    },
    {
        "name": "Срок подачи",
        "type": "date",
    },
    # --- Операционные ---
    {
        "name": "Следующее действие",
        "type": "text",
    },
    {
        "name": "Дата следующего действия",
        "type": "date",
    },
    {
        "name": "Ответственный продажник",
        "type": "text",
    },
    {
        "name": "Ответственный закупщик",
        "type": "text",
    },
    {
        "name": "Команда",
        "type": "select",
        "enums": [
            {"value": "Команда 1"},
            {"value": "Команда 2"},
        ],
    },
    {
        "name": "Нужна закупка / расчёт",
        "type": "checkbox",
    },
    {
        "name": "Есть сомнения СОЗ или реальные торги",
        "type": "checkbox",
    },
    # --- КП и дилер ---
    {
        "name": "Статус КП",
        "type": "select",
        "enums": [
            {"value": "Не начато"},
            {"value": "В работе"},
            {"value": "Готово"},
            {"value": "Отправлено дилеру"},
            {"value": "Невозможно"},
        ],
    },
    {
        "name": "Дилер / канал продаж",
        "type": "text",
    },
    {
        "name": "Решение дилера",
        "type": "select",
        "enums": [
            {"value": "Ожидаем"},
            {"value": "Выходим на торги"},
            {"value": "Отказ"},
        ],
    },
    {
        "name": "Производство",
        "type": "select",
        "enums": [
            {"value": "Не передано"},
            {"value": "Производство 1"},
            {"value": "Производство 2"},
            {"value": "Внешнее"},
        ],
    },
    # --- Закрытие и архив ---
    {
        "name": "Причина закрытия",
        "type": "select",
        "enums": [
            {"value": "В базу / наблюдаем"},
            {"value": "Ждём реальные торги"},
            {"value": "Не наш ассортимент"},
            {"value": "Не успели"},
            {"value": "Нет КП"},
            {"value": "КП невозможно"},
            {"value": "Дилер отказался"},
            {"value": "Вышли на торги"},
            {"value": "Выиграли"},
            {"value": "Проиграли"},
            {"value": "Торги отменены"},
            {"value": "Дубль"},
            {"value": "Требуется повторный обзвон"},
        ],
    },
    {
        "name": "Архивное назначение LLM",
        "type": "select",
        "enums": [
            {"value": "Архив — направления / Специнструмент по чертежам"},
            {"value": "Архив — направления / HSS ГОСТ"},
            {"value": "Архив — направления / Твердосплав"},
            {"value": "Архив — направления / Алмазный"},
            {"value": "Архив — направления / Не наш ассортимент"},
            {"value": "Архив — направления / Дубли / мусор"},
            {"value": "Архив — направления / Требуется проверка"},
            {"value": "Архив — СОЗ / Ждём реальные торги"},
            {"value": "Архив — СОЗ / К обзвону"},
            {"value": "Архив — СОЗ / Повторить через 30 дней"},
            {"value": "Архив — СОЗ / Повторить через 90 дней"},
            {"value": "Архив — СОЗ / Интересный завод"},
            {"value": "Архив — СОЗ / Неактуально"},
        ],
    },
    {
        "name": "Архивное назначение итоговое",
        "type": "select",
        "enums": [
            {"value": "Архив — направления / Специнструмент по чертежам"},
            {"value": "Архив — направления / HSS ГОСТ"},
            {"value": "Архив — направления / Твердосплав"},
            {"value": "Архив — направления / Алмазный"},
            {"value": "Архив — направления / Не наш ассортимент"},
            {"value": "Архив — направления / Дубли / мусор"},
            {"value": "Архив — направления / Требуется проверка"},
            {"value": "Архив — СОЗ / Ждём реальные торги"},
            {"value": "Архив — СОЗ / К обзвону"},
            {"value": "Архив — СОЗ / Повторить через 30 дней"},
            {"value": "Архив — СОЗ / Повторить через 90 дней"},
            {"value": "Архив — СОЗ / Интересный завод"},
            {"value": "Архив — СОЗ / Неактуально"},
        ],
    },
    {
        "name": "Дата возврата из архива",
        "type": "date",
    },
    # --- LLM метаданные ---
    {
        "name": "LLM confidence",
        "type": "numeric",
    },
    {
        "name": "LLM comment",
        "type": "textarea",
    },
    {
        "name": "Manager comment",
        "type": "textarea",
    },
]


def api_request(method, url, data=None, retries=3):
    """Universal API wrapper with rate limiting and retry."""
    for attempt in range(retries):
        time.sleep(RATE_LIMIT_PAUSE)
        try:
            if method == "GET":
                r = requests.get(url, headers=HEADERS, timeout=30)
            elif method == "POST":
                r = requests.post(url, headers=HEADERS, json=data, timeout=30)
            else:
                r = requests.request(method, url, headers=HEADERS, json=data, timeout=30)

            if r.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"    ⚠️  Rate limited (429). Waiting {wait}s...")
                time.sleep(wait)
                continue
            return r
        except requests.exceptions.Timeout:
            print(f"    ⚠️  Timeout (attempt {attempt+1}/{retries})")
            time.sleep(5)
        except requests.exceptions.ConnectionError:
            print(f"    ⚠️  Connection error (attempt {attempt+1}/{retries})")
            time.sleep(10)
    return None


def get_existing_fields():
    """Get list of existing custom fields."""
    r = api_request("GET", f"https://{BASE}/api/v4/leads/custom_fields")
    if r and r.status_code == 200:
        data = r.json()
        return data.get("_embedded", {}).get("custom_fields", [])
    return []


def create_field(field_def):
    """Create a single custom field via API."""
    payload = {
        "name": field_def["name"],
        "type": field_def["type"],
    }

    # Add enum values for select/multiselect
    if "enums" in field_def:
        payload["enums"] = field_def["enums"]

    r = api_request("POST", f"https://{BASE}/api/v4/leads/custom_fields", [payload])
    return r


def main():
    if not APPLY and not DRY_RUN:
        print("Использование:")
        print("  python3 src/create_custom_fields.py --dry-run   # показать план")
        print("  python3 src/create_custom_fields.py --apply     # создать поля")
        sys.exit(0)

    print(f"{'🔍 DRY-RUN' if DRY_RUN else '🚀 APPLYING'} — Создание 33 кастомных полей\n")

    # Get existing fields to avoid duplicates
    print("Проверяю существующие поля...")
    existing = get_existing_fields() if not DRY_RUN else []
    existing_names = {f["name"] for f in existing}
    print(f"  Найдено существующих: {len(existing)}")

    # Filter out already existing fields
    to_create = [f for f in CUSTOM_FIELDS if f["name"] not in existing_names]
    already_exist = [f for f in CUSTOM_FIELDS if f["name"] in existing_names]

    if already_exist:
        print(f"\n  Уже существуют ({len(already_exist)}):")
        for f in already_exist:
            print(f"    ⏭️  {f['name']}")

    print(f"\n  К созданию: {len(to_create)} полей")
    print(f"{'='*60}")

    # Show plan
    for i, field in enumerate(to_create, 1):
        enums_str = ""
        if "enums" in field:
            vals = [e["value"] for e in field["enums"]]
            enums_str = f" [{len(vals)} вариантов: {', '.join(vals[:3])}{'...' if len(vals)>3 else ''}]"
        print(f"  {i:>2}. {field['name']} ({field['type']}){enums_str}")

    if DRY_RUN:
        print(f"\n{'='*60}")
        print("🔍 DRY-RUN завершён. Для применения используйте --apply")
        return

    # Apply
    print(f"\n{'='*60}")
    print("Создаю поля...\n")

    created_count = 0
    failed = []

    for i, field in enumerate(to_create, 1):
        r = create_field(field)
        if r and r.status_code == 200:
            new_id = r.json()["_embedded"]["custom_fields"][0]["id"]
            created_count += 1
            print(f"  ✅ {i:>2}. {field['name']} → id={new_id}")
        else:
            status = r.status_code if r else "NO_RESPONSE"
            body = r.text[:100] if r else "timeout"
            failed.append(field["name"])
            print(f"  ❌ {i:>2}. {field['name']}: {status} {body}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  Создано: {created_count}/{len(to_create)}")
    if failed:
        print(f"  Ошибки: {len(failed)}")
        for f in failed:
            print(f"    - {f}")

    # Final verification
    print("\n  Финальная проверка...")
    final_fields = get_existing_fields()
    custom_count = len([f for f in final_fields if not f.get("is_predefined")])
    print(f"  Всего кастомных полей в amoCRM: {custom_count}")
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
