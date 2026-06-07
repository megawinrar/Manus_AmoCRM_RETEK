"""
setup_pipelines.py — Создание и настройка воронок amoCRM для RETEK

Структура воронок по ТЗ:
  1. «RETEK Тендеры» (активная) — 10 статусов
  2. «Архив — Направления» (архивная) — 5 статусов
  3. «Архив — СОЗ» (архивная) — 4 статуса

Особенности amoCRM API:
  - Цвета при создании (POST) не принимаются — создаём без цвета
  - Цвета устанавливаются через PATCH после создания
  - Серые цвета (#d6d6d6, #c1c1c1, #aaaaaa) не принимаются API — остаётся дефолтный

Запуск:
  python3 src/setup_pipelines.py
"""

import os
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


def api_get(path: str) -> dict:
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def api_patch(path: str, data) -> dict:
    r = requests.patch(f"{BASE_URL}{path}", headers=HEADERS, json=data, timeout=15)
    r.raise_for_status()
    return r.json()


def api_post(path: str, data) -> dict:
    r = requests.post(f"{BASE_URL}{path}", headers=HEADERS, json=data, timeout=15)
    r.raise_for_status()
    return r.json()


def api_delete(path: str) -> bool:
    r = requests.delete(f"{BASE_URL}{path}", headers=HEADERS, timeout=15)
    return r.status_code in (200, 204)


# ─────────────────────────────────────────────────────────────────────────────
# Допустимые цвета amoCRM (серые не принимаются через API — используем None)
# ─────────────────────────────────────────────────────────────────────────────
C = {
    "default":     None,        # серый — дефолтный, не устанавливается через API
    "yellow_lt":   "#fffeb2",   # светло-жёлтый
    "yellow":      "#fffd7f",   # жёлтый
    "yellow_dk":   "#fff000",   # насыщенный жёлтый
    "peach_lt":    "#ffeab2",   # светло-персиковый
    "peach":       "#ffdc7f",   # персиковый
    "orange":      "#ffce5a",   # оранжевый
    "red_lt":      "#ffdbdb",   # светло-красный
    "red":         "#ffc8c8",   # красный
    "red_dk":      "#ff8f92",   # насыщенный красный
    "blue_lt":     "#d6eaff",   # светло-голубой
    "blue":        "#c1e0ff",   # голубой
    "blue_dk":     "#98cbff",   # насыщенный голубой
    "green_lt":    "#ebffb1",   # светло-зелёный
    "green":       "#deff81",   # зелёный
    "green_dk":    "#87f2c0",   # насыщенный зелёный (мята)
    "purple_lt":   "#f9deff",   # светло-фиолетовый
    "purple":      "#f3beff",   # фиолетовый
    "purple_dk":   "#ccc8f9",   # насыщенный фиолетовый (индиго)
}

# ─────────────────────────────────────────────────────────────────────────────
# Определение воронок и статусов
# ─────────────────────────────────────────────────────────────────────────────

ACTIVE_PIPELINE_NAME = "RETEK Тендеры"
ACTIVE_STATUSES = [
    {"name": "1. Новый тендер",            "color": C["default"]},     # серый
    {"name": "2. Квалификация",            "color": C["yellow_lt"]},   # жёлтый
    {"name": "3. Расчёт стоимости",        "color": C["orange"]},      # оранжевый
    {"name": "4. Решение принято",         "color": C["blue_lt"]},     # голубой
    {"name": "5. Подача заявки",           "color": C["blue_dk"]},     # синий
    {"name": "6. Ожидание результата",     "color": C["purple_dk"]},   # индиго
    {"name": "7. Победа — оформление",     "color": C["green"]},       # зелёный
    {"name": "8. Поставка / Исполнение",   "color": C["green_dk"]},    # мята
    {"name": "9. Закрыт — отказ/проигрыш", "color": C["red_dk"]},     # красный
    {"name": "10. Готов к архивации",      "color": C["purple"]},      # фиолетовый
]

ARCHIVE_DIR_PIPELINE_NAME = "Архив — Направления"
ARCHIVE_DIR_STATUSES = [
    {"name": "Специнструмент по чертежам", "color": C["blue_dk"]},
    {"name": "HSS / ГОСТ",                 "color": C["green_dk"]},
    {"name": "Твердосплав",                "color": C["orange"]},
    {"name": "Алмазный инструмент",        "color": C["purple"]},
    {"name": "Прочее",                     "color": C["default"]},
]

ARCHIVE_SOZ_PIPELINE_NAME = "Архив — СОЗ"
ARCHIVE_SOZ_STATUSES = [
    {"name": "СОЗ — Победа",    "color": C["green"]},
    {"name": "СОЗ — Проигрыш", "color": C["red_dk"]},
    {"name": "СОЗ — Отмена",   "color": C["default"]},
    {"name": "СОЗ — Прочее",   "color": C["yellow_lt"]},
]


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def get_existing_pipelines() -> list:
    data = api_get("/leads/pipelines")
    return data.get("_embedded", {}).get("pipelines", [])


def get_pipeline_statuses(pipeline_id: int) -> list:
    data = api_get(f"/leads/pipelines/{pipeline_id}")
    return data.get("_embedded", {}).get("statuses", [])


def rename_pipeline(pipeline_id: int, new_name: str):
    print(f"  → Переименовываю [{pipeline_id}] → «{new_name}»...")
    api_patch(f"/leads/pipelines/{pipeline_id}", {"name": new_name})
    print(f"    ✓ Готово")


def delete_custom_statuses(pipeline_id: int, statuses: list):
    """Удаляет все кастомные статусы (кроме системных 142 и 143 и Неразобранного)."""
    system_ids = {142, 143}
    deleted = 0
    for s in statuses:
        if s["id"] in system_ids or s.get("type") == 10000:  # Неразобранное
            continue
        if api_delete(f"/leads/pipelines/{pipeline_id}/statuses/{s['id']}"):
            print(f"    ✓ Удалён [{s['id']}] {s['name']}")
            deleted += 1
        else:
            print(f"    ⚠ Не удалось удалить [{s['id']}] {s['name']}")
    return deleted


def create_statuses_with_colors(pipeline_id: int, statuses: list) -> list:
    """
    Создаёт статусы в воронке:
    1. POST без цвета (API не принимает цвет при создании)
    2. PATCH цвет для каждого статуса (кроме серых — они дефолтные)
    """
    created_ids = []

    for i, s in enumerate(statuses):
        # Шаг 1: создаём статус без цвета
        payload = [{"name": s["name"], "sort": (i + 1) * 10}]
        result = api_post(f"/leads/pipelines/{pipeline_id}/statuses", payload)
        created = result.get("_embedded", {}).get("statuses", [])
        if not created:
            print(f"    ✗ Не удалось создать «{s['name']}»")
            continue

        sid = created[0]["id"]
        created_ids.append(sid)

        # Шаг 2: устанавливаем цвет через PATCH (если не дефолтный)
        if s["color"] is not None:
            try:
                api_patch(f"/leads/pipelines/{pipeline_id}/statuses/{sid}", {"color": s["color"]})
                print(f"    ✓ [{sid}] {s['name']} ({s['color']})")
            except Exception:
                print(f"    ~ [{sid}] {s['name']} (цвет не установлен)")
        else:
            print(f"    ✓ [{sid}] {s['name']} (дефолтный цвет)")

        time.sleep(0.1)  # небольшая пауза между запросами

    return created_ids


def create_new_pipeline(name: str, statuses: list, is_archive: bool = False) -> int:
    """Создаёт новую воронку, затем добавляет статусы."""
    print(f"\n  \u2192 Создаю воронку \u00ab{name}\u00bb...")
    # amoCRM требует is_main, is_unsorted_on и _embedded.statuses при создании
    payload = [{
        "name": name,
        "sort": 100,
        "is_main": False,
        "is_unsorted_on": False,
        "_embedded": {
            "statuses": [{"name": "_init", "sort": 10}]
        }
    }]
    result = api_post("/leads/pipelines", payload)
    pipelines = result.get("_embedded", {}).get("pipelines", [])
    if not pipelines:
        raise RuntimeError(f"Не удалось создать воронку «{name}»")

    p = pipelines[0]
    pid = p["id"]
    print(f"    \u2713 Воронка создана [{pid}]")

    # Удаляем временный _init статус
    init_statuses = p.get("_embedded", {}).get("statuses", [])
    for s in init_statuses:
        if s.get("name") == "_init":
            api_delete(f"/leads/pipelines/{pid}/statuses/{s['id']}")

    print(f"  \u2192 Добавляю статусы ({len(statuses)} шт.)...")
    create_statuses_with_colors(pid, statuses)
    return pid


def save_pipeline_ids(active_id: int, archive_dir_id: int, archive_soz_id: int):
    """Сохраняет ID воронок в .env файл."""
    env_path = Path(__file__).parent.parent / ".env"
    content = env_path.read_text(encoding="utf-8")

    def upsert(text: str, key: str, value) -> str:
        lines = text.splitlines()
        new_lines, found = [], False
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}")
        return "\n".join(new_lines) + "\n"

    content = upsert(content, "AMO_PIPELINE_ACTIVE_ID", active_id)
    content = upsert(content, "AMO_PIPELINE_ARCHIVE_DIRECTIONS_ID", archive_dir_id)
    content = upsert(content, "AMO_PIPELINE_ARCHIVE_SOZ_ID", archive_soz_id)
    env_path.write_text(content, encoding="utf-8")
    print(f"\n  ✓ ID воронок сохранены в .env")


# ─────────────────────────────────────────────────────────────────────────────
# Основной сценарий
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("RETEK amoCRM — Настройка воронок")
    print("=" * 60)

    existing = get_existing_pipelines()
    print(f"\n[1] Существующие воронки: {len(existing)}")
    for p in existing:
        print(f"    [{p['id']}] {p['name']}")

    active_id = archive_dir_id = archive_soz_id = None

    # ── Активная воронка ──────────────────────────────────────────────────────
    print(f"\n[2] Активная воронка «{ACTIVE_PIPELINE_NAME}»")
    if existing:
        first = existing[0]
        active_id = first["id"]
        rename_pipeline(active_id, ACTIVE_PIPELINE_NAME)

        statuses = get_pipeline_statuses(active_id)
        print(f"  → Удаляю старые статусы ({len(statuses)} шт.)...")
        delete_custom_statuses(active_id, statuses)

        print(f"  → Создаю новые статусы ({len(ACTIVE_STATUSES)} шт.)...")
        create_statuses_with_colors(active_id, ACTIVE_STATUSES)
    else:
        active_id = create_new_pipeline(ACTIVE_PIPELINE_NAME, ACTIVE_STATUSES, is_archive=False)

    # ── Архив — Направления ───────────────────────────────────────────────────
    print(f"\n[3] Архивная воронка «{ARCHIVE_DIR_PIPELINE_NAME}»")
    if len(existing) >= 2:
        second = existing[1]
        archive_dir_id = second["id"]
        rename_pipeline(archive_dir_id, ARCHIVE_DIR_PIPELINE_NAME)

        statuses = get_pipeline_statuses(archive_dir_id)
        print(f"  → Удаляю старые статусы ({len(statuses)} шт.)...")
        delete_custom_statuses(archive_dir_id, statuses)

        print(f"  → Создаю новые статусы ({len(ARCHIVE_DIR_STATUSES)} шт.)...")
        create_statuses_with_colors(archive_dir_id, ARCHIVE_DIR_STATUSES)
    else:
        archive_dir_id = create_new_pipeline(ARCHIVE_DIR_PIPELINE_NAME, ARCHIVE_DIR_STATUSES, is_archive=True)

    # ── Архив — СОЗ ───────────────────────────────────────────────────────────
    print(f"\n[4] Архивная воронка «{ARCHIVE_SOZ_PIPELINE_NAME}»")
    archive_soz_id = create_new_pipeline(ARCHIVE_SOZ_PIPELINE_NAME, ARCHIVE_SOZ_STATUSES, is_archive=True)

    # ── Сохраняем ID ─────────────────────────────────────────────────────────
    save_pipeline_ids(active_id, archive_dir_id, archive_soz_id)

    # ── Итог ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ИТОГ:")
    print(f"  Активная воронка:        [{active_id}] {ACTIVE_PIPELINE_NAME}")
    print(f"  Архив — Направления:     [{archive_dir_id}] {ARCHIVE_DIR_PIPELINE_NAME}")
    print(f"  Архив — СОЗ:             [{archive_soz_id}] {ARCHIVE_SOZ_PIPELINE_NAME}")
    print("=" * 60)
    print("\n✅ Воронки настроены успешно!")


if __name__ == "__main__":
    main()
