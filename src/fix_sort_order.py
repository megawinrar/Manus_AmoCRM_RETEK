"""
fix_sort_order.py
-----------------
Исправляет порядок колонок в Канбан воронки «RETEK Тендеры».

amoCRM рендерит Канбан: слева = наибольший sort.
Целевой порядок слева→направо:
  1. Новый тендер → 2. Квалификация → ... → 10. Готов к архивации → Неразобранное

Запуск:
  python3 src/fix_sort_order.py --dry-run   # только показать план
  python3 src/fix_sort_order.py             # применить
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

DOMAIN  = os.getenv("AMO_DOMAIN")
TOKEN   = os.getenv("AMO_ACCESS_TOKEN")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
PIPELINE_ID = 10984442

# Целевой sort: чем больше — тем левее в Канбан.
# Системные статусы (142, 143) не трогаем — у них sort 10000/11000, они всегда крайние слева.
# Неразобранное (86352246) ставим sort=50 — крайнее справа среди кастомных.
TARGET_SORT = {
    "1. Новый тендер":            1100,
    "2. Квалификация":            1000,
    "3. Расчёт стоимости":         900,
    "4. Решение принято":          800,
    "5. Подача заявки":            700,
    "6. Ожидание результата":      600,
    "7. Победа — оформление":      500,
    "8. Поставка / Исполнение":    400,
    "9. Закрыт — отказ/проигрыш":  300,
    "10. Готов к архивации":       200,
    "Неразобранное":                50,
}

SYSTEM_IDS = {142, 143}  # Успешно реализовано / Закрыто и не реализовано — не трогаем

DRY_RUN = "--dry-run" in sys.argv


def get_statuses():
    r = requests.get(
        f"https://{DOMAIN}/api/v4/leads/pipelines/{PIPELINE_ID}",
        headers=HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("_embedded", {}).get("statuses", [])


def patch_sort(status_id, new_sort, name):
    if DRY_RUN:
        return True
    r = requests.patch(
        f"https://{DOMAIN}/api/v4/leads/pipelines/{PIPELINE_ID}/statuses/{status_id}",
        headers=HEADERS,
        json={"id": status_id, "sort": new_sort},
        timeout=10,
    )
    time.sleep(0.3)
    return r.status_code in (200, 204)


def main():
    print("=" * 60)
    if DRY_RUN:
        print("DRY-RUN — план изменений (реальных запросов нет)")
    else:
        print("RETEK amoCRM — Исправление порядка колонок Канбан")
    print("=" * 60)

    statuses = get_statuses()
    statuses_by_name = {s["name"]: s for s in statuses}

    print(f"\nТекущий порядок (слева→направо в Канбан = убывание sort):")
    for s in sorted(statuses, key=lambda x: x["sort"], reverse=True):
        marker = "  [системный]" if s["id"] in SYSTEM_IDS else ""
        print(f"  sort={s['sort']:>6}  [{s['id']}]  {s['name']}{marker}")

    print(f"\nПлан изменений:")
    changes = []
    for name, new_sort in TARGET_SORT.items():
        if name not in statuses_by_name:
            print(f"  ⚠ Статус '{name}' не найден в воронке — пропускаю")
            continue
        s = statuses_by_name[name]
        old_sort = s["sort"]
        if old_sort == new_sort:
            print(f"  = [{s['id']}] '{name}' sort={old_sort} — без изменений")
        else:
            print(f"  ✎ [{s['id']}] '{name}' sort: {old_sort} → {new_sort}")
            changes.append((s["id"], new_sort, name))

    if not changes:
        print("\n✅ Все sort уже корректны, изменений не требуется.")
        return

    if DRY_RUN:
        print(f"\nИтого: {len(changes)} статусов будут обновлены.")
        print("Запустите без --dry-run чтобы применить.")
        return

    print(f"\nПрименяю {len(changes)} изменений...")
    ok = 0
    for status_id, new_sort, name in changes:
        if patch_sort(status_id, new_sort, name):
            print(f"  ✓ '{name}' → sort={new_sort}")
            ok += 1
        else:
            print(f"  ✗ Ошибка при обновлении '{name}'")

    print(f"\nОбновлено {ok}/{len(changes)} статусов.")

    # Финальная проверка
    print("\nФинальный порядок в Канбан (слева→направо):")
    statuses2 = get_statuses()
    for i, s in enumerate(sorted(statuses2, key=lambda x: x["sort"], reverse=True), 1):
        marker = " [системный]" if s["id"] in SYSTEM_IDS else ""
        print(f"  {i:>2}. {s['name']}{marker}  (sort={s['sort']})")

    print("\n✅ Готово! Обновите страницу amoCRM чтобы увидеть новый порядок.")


if __name__ == "__main__":
    main()
