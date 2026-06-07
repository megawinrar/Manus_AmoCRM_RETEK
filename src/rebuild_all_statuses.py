"""
Пересоздание статусов всех воронок amoCRM по PATCH5 ТЗ.
Использование:
    python3 src/rebuild_all_statuses.py --dry-run   # показать план
    python3 src/rebuild_all_statuses.py --apply     # применить
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
RATE_LIMIT_PAUSE = 1.5  # секунд между запросами

# === ЦЕЛЕВАЯ КОНФИГУРАЦИЯ ПО PATCH5 ТЗ ===

ACTIVE_PIPELINE_ID = 10984442
ARCHIVE_DIRECTIONS_ID = 10984454
ARCHIVE_SOZ_ID = 10985038

# Активная воронка — канонические статусы
# sort: больший = левее в Канбан. Нумерация 1→10 слева→направо = sort 1100→200
ACTIVE_STATUSES = [
    {"name": "1. LLM распознал",                 "sort": 1100, "color": "#fffeb2"},
    {"name": "2. Проверка Сотрудника 2",         "sort": 1000, "color": "#fffeb2"},
    {"name": "3. СОЗ — звонок / уточнить дату",  "sort": 900,  "color": "#ffce5a"},
    {"name": "4. СОЗ — ждём реальный торг",      "sort": 800,  "color": "#ffce5a"},
    {"name": "5. Передано в закупку / расчёт",   "sort": 700,  "color": "#d6eaff"},
    {"name": "6. КП готовится",                  "sort": 600,  "color": "#98cbff"},
    {"name": "7. КП передано дилеру",            "sort": 500,  "color": "#ccc8f9"},
    {"name": "8. Решение дилера",                "sort": 400,  "color": "#f3beff"},
    {"name": "9. Передано в производство",       "sort": 300,  "color": "#deff81"},
    {"name": "10. К архивированию",              "sort": 200,  "color": "#87f2c0"},
]

# Архив — направления
ARCHIVE_DIRECTIONS_STATUSES = [
    {"name": "Специнструмент по чертежам", "sort": 700, "color": "#98cbff"},
    {"name": "HSS / ГОСТ",                 "sort": 600, "color": "#d6eaff"},
    {"name": "Твердосплав",                "sort": 500, "color": "#ffce5a"},
    {"name": "Алмазный",                   "sort": 400, "color": "#ccc8f9"},
    {"name": "Не наш ассортимент",         "sort": 300, "color": "#ff8f92"},
    {"name": "Дубли / мусор",              "sort": 200, "color": "#ffc8c8"},
    {"name": "Требуется проверка",         "sort": 100, "color": "#fffeb2"},
]

# Архив — СОЗ / развитие
ARCHIVE_SOZ_STATUSES = [
    {"name": "СОЗ — ждём реальные торги",  "sort": 600, "color": "#ffce5a"},
    {"name": "К обзвону",                  "sort": 500, "color": "#fffeb2"},
    {"name": "Повторить через 30 дней",    "sort": 400, "color": "#d6eaff"},
    {"name": "Повторить через 90 дней",    "sort": 300, "color": "#98cbff"},
    {"name": "Интересный завод",           "sort": 200, "color": "#deff81"},
    {"name": "Неактуально",                "sort": 100, "color": "#ffc8c8"},
]

# Системные статусы которые нельзя удалить
SYSTEM_STATUS_IDS = {142, 143}
SYSTEM_NAMES = {"Неразобранное"}


def api_request(method, url, json_data=None, retries=3):
    """Выполнить запрос к API с retry и rate limiting."""
    for attempt in range(retries):
        try:
            r = requests.request(method, url, headers=HEADERS, json=json_data, timeout=30)
            if r.status_code == 429:
                print(f"  ⚠️  Rate limit (429), пауза 5с...")
                time.sleep(5)
                continue
            return r
        except requests.exceptions.Timeout:
            print(f"  ⚠️  Timeout (attempt {attempt+1}/{retries}), пауза 3с...")
            time.sleep(3)
        except requests.exceptions.ConnectionError:
            print(f"  ⚠️  Connection error (attempt {attempt+1}/{retries}), пауза 5с...")
            time.sleep(5)
    return None


def get_pipeline_statuses(pipeline_id):
    """Получить текущие статусы воронки."""
    r = api_request("GET", f"https://{BASE}/api/v4/leads/pipelines/{pipeline_id}/statuses")
    if r and r.status_code == 200:
        return r.json().get("_embedded", {}).get("statuses", [])
    print(f"  ❌ Не удалось получить статусы pipeline {pipeline_id}: {r.status_code if r else 'no response'}")
    return []


def delete_status(pipeline_id, status_id):
    """Удалить статус."""
    time.sleep(RATE_LIMIT_PAUSE)
    r = api_request("DELETE", f"https://{BASE}/api/v4/leads/pipelines/{pipeline_id}/statuses/{status_id}")
    if r and r.status_code in (200, 204):
        return True
    print(f"  ❌ DELETE failed: status {status_id}, code={r.status_code if r else '?'}")
    return False


def create_statuses_batch(pipeline_id, statuses_list):
    """Создать статусы одним POST-запросом (массив)."""
    time.sleep(RATE_LIMIT_PAUSE)
    # POST принимает массив, но игнорирует sort
    payload = [{"name": s["name"]} for s in statuses_list]
    r = api_request("POST", f"https://{BASE}/api/v4/leads/pipelines/{pipeline_id}/statuses", json_data=payload)
    if r and r.status_code == 200:
        created = r.json().get("_embedded", {}).get("statuses", [])
        return created
    print(f"  ❌ POST batch failed: code={r.status_code if r else '?'}, body={r.text[:200] if r else '?'}")
    return []


def patch_status(pipeline_id, status_id, name, sort, color):
    """PATCH статуса с ОБЯЗАТЕЛЬНЫМИ name + sort + color."""
    time.sleep(RATE_LIMIT_PAUSE)
    payload = {"name": name, "sort": sort, "color": color}
    r = api_request("PATCH", f"https://{BASE}/api/v4/leads/pipelines/{pipeline_id}/statuses/{status_id}", json_data=payload)
    if r and r.status_code == 200:
        return True
    print(f"  ❌ PATCH failed: status {status_id}, code={r.status_code if r else '?'}, body={r.text[:200] if r else '?'}")
    return False


def rebuild_pipeline(pipeline_id, target_statuses, dry_run=True):
    """Пересоздать статусы в воронке."""
    print(f"\n{'[DRY-RUN]' if dry_run else '[APPLY]'} Pipeline ID: {pipeline_id}")
    
    # 1. Получить текущие статусы
    current = get_pipeline_statuses(pipeline_id)
    
    # 2. Определить что удалять (всё кроме системных)
    to_delete = [s for s in current if s["id"] not in SYSTEM_STATUS_IDS and s["name"] not in SYSTEM_NAMES]
    
    print(f"  Текущих статусов: {len(current)} (из них системных: {len(current) - len(to_delete)})")
    print(f"  К удалению: {len(to_delete)}")
    print(f"  К созданию: {len(target_statuses)}")
    
    if dry_run:
        print("\n  Будут удалены:")
        for s in to_delete:
            print(f"    ❌ id={s['id']} name='{s['name']}' sort={s['sort']}")
        print("\n  Будут созданы:")
        for s in target_statuses:
            print(f"    ✅ name='{s['name']}' sort={s['sort']} color={s['color']}")
        return True
    
    # 3. Удалить старые
    print("  Удаляю старые статусы...")
    for s in to_delete:
        ok = delete_status(pipeline_id, s["id"])
        print(f"    {'✅' if ok else '❌'} Удалён: '{s['name']}' (id={s['id']})")
    
    # 4. Создать новые (batch POST)
    print("  Создаю новые статусы (batch)...")
    created = create_statuses_batch(pipeline_id, target_statuses)
    if not created:
        print("  ❌ Batch creation failed!")
        return False
    print(f"    ✅ Создано: {len(created)} статусов")
    
    # 5. PATCH каждый с name + sort + color
    print("  Применяю sort + color через PATCH...")
    # Сопоставляем по порядку (created в том же порядке что и payload)
    for i, (created_s, target_s) in enumerate(zip(created, target_statuses)):
        ok = patch_status(pipeline_id, created_s["id"], target_s["name"], target_s["sort"], target_s["color"])
        print(f"    {'✅' if ok else '❌'} PATCH: '{target_s['name']}' sort={target_s['sort']} color={target_s['color']}")
    
    # 6. Верификация
    print("  Верификация...")
    time.sleep(RATE_LIMIT_PAUSE)
    final = get_pipeline_statuses(pipeline_id)
    custom = [s for s in final if s["id"] not in SYSTEM_STATUS_IDS and s["name"] not in SYSTEM_NAMES]
    print(f"    Итого кастомных статусов: {len(custom)}")
    for s in sorted(custom, key=lambda x: -x["sort"]):
        print(f"    sort={s['sort']:>5} | {s['name']}")
    
    return True


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    dry_run = mode != "--apply"
    
    if dry_run:
        print("=" * 60)
        print("  РЕЖИМ DRY-RUN — изменения НЕ применяются")
        print("=" * 60)
    else:
        print("=" * 60)
        print("  РЕЖИМ APPLY — изменения БУДУТ применены к amoCRM!")
        print("=" * 60)
    
    # Активная воронка
    print("\n" + "=" * 60)
    print("  RETEK Тендеры (активная)")
    print("=" * 60)
    rebuild_pipeline(ACTIVE_PIPELINE_ID, ACTIVE_STATUSES, dry_run)
    
    # Архив — направления
    print("\n" + "=" * 60)
    print("  Архив — Направления")
    print("=" * 60)
    rebuild_pipeline(ARCHIVE_DIRECTIONS_ID, ARCHIVE_DIRECTIONS_STATUSES, dry_run)
    
    # Архив — СОЗ
    print("\n" + "=" * 60)
    print("  Архив — СОЗ")
    print("=" * 60)
    rebuild_pipeline(ARCHIVE_SOZ_ID, ARCHIVE_SOZ_STATUSES, dry_run)
    
    print("\n" + "=" * 60)
    if dry_run:
        print("  DRY-RUN завершён. Для применения: python3 src/rebuild_all_statuses.py --apply")
    else:
        print("  ✅ ВСЕ ВОРОНКИ ПЕРЕСТРОЕНЫ!")
    print("=" * 60)


if __name__ == "__main__":
    main()
