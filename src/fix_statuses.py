"""
fix_statuses.py — Настройка статусов активной воронки RETEK Тендеры

ВАЖНО: amoCRM API при PATCH статуса сбрасывает имя, если не передать его повторно.
Решение: PATCH всегда содержит и name, и color одновременно.

Режимы запуска:
  python3 src/fix_statuses.py --dry-run   # показать план без изменений
  python3 src/fix_statuses.py             # применить изменения

Тесты:
  python3 -m pytest tests/ -v
"""

import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

DOMAIN  = os.getenv("AMO_DOMAIN")
TOKEN   = os.getenv("AMO_ACCESS_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}
BASE_URL = f"https://{DOMAIN}/api/v4"

ACTIVE_PIPELINE_ID = int(os.getenv("AMO_PIPELINE_ACTIVE_ID", "10984442"))

# ─────────────────────────────────────────────────────────────────────────────
# Допустимые цвета amoCRM (серые #d6d6d6, #c1c1c1, #aaaaaa — НЕ принимаются)
# ─────────────────────────────────────────────────────────────────────────────
# None = дефолтный цвет (создаётся без color, API сам назначит)

ACTIVE_STATUSES = [
    {
        "name":  "1. Новый тендер",
        "color": None,
        "sort":  1000,
        "desc":  "Тендер только поступил. Ещё не квалифицирован. Задача: проверить ТЗ, сроки, НМЦ и передать на квалификацию.",
    },
    {
        "name":  "2. Квалификация",
        "color": "#fffeb2",
        "sort":  900,
        "desc":  "Сотрудник изучает тендер: приоритет (Р1–Р4), направление, наличие ТЗ/чертежей. Р4 → сразу в архив. Р1–Р3 → расчёт.",
    },
    {
        "name":  "3. Расчёт стоимости",
        "color": "#ffce5a",
        "sort":  800,
        "desc":  "Закупщик считает себестоимость. Продажник формирует цену с маржой. Срок: до дедлайна подачи минус 1 день.",
    },
    {
        "name":  "4. Решение принято",
        "color": "#d6eaff",
        "sort":  700,
        "desc":  "Руководитель одобрил участие и цену. Заявка готова к подаче. Ждём подтверждения от закупщика.",
    },
    {
        "name":  "5. Подача заявки",
        "color": "#98cbff",
        "sort":  600,
        "desc":  "Заявка подана на площадку. Зафиксировать дату подачи и номер заявки. Ждём даты торгов.",
    },
    {
        "name":  "6. Ожидание результата",
        "color": "#ccc8f9",
        "sort":  500,
        "desc":  "Торги прошли или итоги ещё не объявлены. Следить за протоколом на площадке. Срок проверки — дата торгов + 1 день.",
    },
    {
        "name":  "7. Победа — оформление",
        "color": "#deff81",
        "sort":  400,
        "desc":  "Мы победили! Подписываем договор, выставляем счёт, согласуем спецификацию. Контроль: не пропустить срок подписания.",
    },
    {
        "name":  "8. Поставка / Исполнение",
        "color": "#87f2c0",
        "sort":  300,
        "desc":  "Договор подписан. Идёт производство или закупка товара. Контроль: срок поставки по договору.",
    },
    {
        "name":  "9. Закрыт — отказ/проигрыш",
        "color": "#ff8f92",
        "sort":  200,
        "desc":  "Не участвовали, проиграли торги или отказались. Указать причину в поле «Причина закрытия». Готов к архивации.",
    },
    {
        "name":  "10. Готов к архивации",
        "color": "#f3beff",
        "sort":  100,
        "desc":  "Сделка завершена (победа исполнена или отказ зафиксирован). Микросервис-архиватор перенесёт её в архивную воронку автоматически.",
    },
]

SYSTEM_STATUS_IDS = {142, 143}


# ─────────────────────────────────────────────────────────────────────────────
# API-клиент
# ─────────────────────────────────────────────────────────────────────────────

def api_get(path: str) -> dict:
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def api_post(path: str, data: list) -> dict:
    r = requests.post(f"{BASE_URL}{path}", headers=HEADERS, json=data, timeout=15)
    r.raise_for_status()
    return r.json()


def api_patch(path: str, data: dict) -> dict:
    r = requests.patch(f"{BASE_URL}{path}", headers=HEADERS, json=data, timeout=15)
    r.raise_for_status()
    return r.json()


def api_delete(path: str) -> bool:
    r = requests.delete(f"{BASE_URL}{path}", headers=HEADERS, timeout=15)
    return r.status_code in (200, 204)


# ─────────────────────────────────────────────────────────────────────────────
# Бизнес-логика
# ─────────────────────────────────────────────────────────────────────────────

def get_statuses(pipeline_id: int) -> list:
    data = api_get(f"/leads/pipelines/{pipeline_id}")
    return data.get("_embedded", {}).get("statuses", [])


def delete_custom_statuses(pipeline_id: int, statuses: list):
    """Удаляет все кастомные статусы (кроме системных и Неразобранного)."""
    for s in statuses:
        if s["id"] in SYSTEM_STATUS_IDS:
            continue
        if s.get("type") == 10000:  # Неразобранное — нельзя удалить
            print(f"  ~ Пропускаю системный [{s['id']}] {s['name']}")
            continue
        if api_delete(f"/leads/pipelines/{pipeline_id}/statuses/{s['id']}"):
            print(f"  ✓ Удалён [{s['id']}] {repr(s['name'])}")
        else:
            print(f"  ✗ Не удалось удалить [{s['id']}] {repr(s['name'])}")
        time.sleep(0.05)


def create_status_with_name_and_color(
    pipeline_id: int, name: str, color, sort: int
) -> int:
    """
    Создаёт статус с именем и цветом.

    Особенность amoCRM API:
    - POST принимает имя, но НЕ принимает цвет
    - PATCH принимает и имя, и цвет — передаём оба, чтобы имя не сбрасывалось

    Если color=None — PATCH не делаем (остаётся дефолтный цвет).
    """
    # Шаг 1: создаём статус с именем
    payload = [{"name": name, "sort": sort}]
    result = api_post(f"/leads/pipelines/{pipeline_id}/statuses", payload)
    created = result.get("_embedded", {}).get("statuses", [])
    if not created:
        raise RuntimeError(f"Не удалось создать статус «{name}»")
    sid = created[0]["id"]

    # Шаг 2: PATCH с именем + цветом (если цвет задан)
    if color is not None:
        api_patch(
            f"/leads/pipelines/{pipeline_id}/statuses/{sid}",
            {"name": name, "color": color}  # имя передаём повторно!
        )

    return sid


def dry_run_report(pipeline_id: int) -> dict:
    """
    Анализирует текущее состояние воронки и возвращает план изменений
    БЕЗ выполнения каких-либо изменений.
    """
    current = get_statuses(pipeline_id)

    to_delete = [
        s for s in current
        if s["id"] not in SYSTEM_STATUS_IDS and s.get("type") != 10000
    ]
    to_keep = [
        s for s in current
        if s["id"] in SYSTEM_STATUS_IDS or s.get("type") == 10000
    ]
    to_create = ACTIVE_STATUSES

    return {
        "current_count": len(current),
        "to_delete": to_delete,
        "to_keep": to_keep,
        "to_create": to_create,
    }


def print_dry_run(pipeline_id: int):
    """Печатает план изменений без выполнения."""
    report = dry_run_report(pipeline_id)

    print("=" * 60)
    print("DRY-RUN — план изменений (реальных запросов нет)")
    print("=" * 60)
    print(f"\nТекущих статусов в воронке: {report['current_count']}")

    print(f"\n[УДАЛИТЬ] {len(report['to_delete'])} статусов:")
    for s in report["to_delete"]:
        print(f"  - [{s['id']}] {repr(s['name'])}")

    print(f"\n[ОСТАВИТЬ] {len(report['to_keep'])} системных статусов:")
    for s in report["to_keep"]:
        print(f"  ~ [{s['id']}] {s['name']}")

    print(f"\n[СОЗДАТЬ] {len(report['to_create'])} статусов:")
    for s in report["to_create"]:
        color_str = s["color"] if s["color"] else "дефолтный"
        print(f"  + {s['name']} ({color_str})")
        print(f"    Описание: {s['desc']}")

    print("\n" + "=" * 60)
    print("Запустите без --dry-run чтобы применить изменения.")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Основной сценарий
# ─────────────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False):
    if dry_run:
        print_dry_run(ACTIVE_PIPELINE_ID)
        return

    print("=" * 60)
    print("RETEK amoCRM — Настройка статусов активной воронки")
    print(f"Воронка ID: {ACTIVE_PIPELINE_ID}")
    print("=" * 60)

    # Текущие статусы
    current = get_statuses(ACTIVE_PIPELINE_ID)
    print(f"\n[1] Текущих статусов: {len(current)}")
    for s in current:
        print(f"    [{s['id']}] {repr(s['name'])} sort={s['sort']}")

    # Удаляем кастомные
    print(f"\n[2] Удаляю кастомные статусы...")
    delete_custom_statuses(ACTIVE_PIPELINE_ID, current)

    # Создаём новые
    print(f"\n[3] Создаю статусы ({len(ACTIVE_STATUSES)} шт.)...")
    for s in ACTIVE_STATUSES:
        sid = create_status_with_name_and_color(
            ACTIVE_PIPELINE_ID, s["name"], s["color"], s["sort"]
        )
        color_str = s["color"] if s["color"] else "дефолтный"
        print(f"  ✓ [{sid}] {s['name']} ({color_str})")
        time.sleep(0.15)

    # Финальная проверка
    print(f"\n[4] Проверка...")
    final = get_statuses(ACTIVE_PIPELINE_ID)
    ok = True
    for s in ACTIVE_STATUSES:
        found = next((f for f in final if f["name"] == s["name"]), None)
        if found:
            print(f"  ✓ {s['name']} [{found['id']}] {found['color']}")
        else:
            print(f"  ✗ НЕ НАЙДЕН: {s['name']}")
            ok = False

    print("\n" + "=" * 60)
    if ok:
        print("✅ Все статусы настроены корректно!")
    else:
        print("⚠ Некоторые статусы не найдены — проверьте вручную.")
    print("=" * 60)

    # Справка по описаниям
    print("\nОписания этапов для сотрудников:")
    print("-" * 60)
    for s in ACTIVE_STATUSES:
        print(f"\n  {s['name']}")
        print(f"  → {s['desc']}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
