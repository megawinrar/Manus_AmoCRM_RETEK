"""
rebuild_statuses.py
-------------------
Полная пересборка статусов активной воронки RETEK Тендеры.

Лимиты amoCRM API:
  - Не более 7 запросов в секунду на интеграцию
  - Не более 50 запросов в секунду на аккаунт
  - При превышении → HTTP 429, при многократном → блокировка 403

Стратегия: 1 запрос в секунду (с запасом), retry при 429 с паузой 5с.

Запуск:
  python3 src/rebuild_statuses.py --dry-run   # только показать план
  python3 src/rebuild_statuses.py             # применить
"""

import os, sys, time, requests
from dotenv import load_dotenv

load_dotenv()

DOMAIN      = os.getenv("AMO_DOMAIN")
TOKEN       = os.getenv("AMO_ACCESS_TOKEN")
HEADERS     = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
PIPELINE_ID = 10984442
SYSTEM_IDS  = {142, 143}
DRY_RUN     = "--dry-run" in sys.argv

# Минимальная пауза между запросами (секунды)
RATE_DELAY = 1.5

# ─── Эталонный список статусов ────────────────────────────────────────────────
STATUSES = [
    {"name": "1. Новый тендер",            "color": None,      "sort": 1100},
    {"name": "2. Квалификация",            "color": "#fffeb2", "sort": 1000},
    {"name": "3. Расчёт стоимости",        "color": "#ffce5a", "sort": 900},
    {"name": "4. Решение принято",         "color": "#d6eaff", "sort": 800},
    {"name": "5. Подача заявки",           "color": "#98cbff", "sort": 700},
    {"name": "6. Ожидание результата",     "color": "#ccc8f9", "sort": 600},
    {"name": "7. Победа — оформление",     "color": "#deff81", "sort": 500},
    {"name": "8. Поставка / Исполнение",   "color": "#87f2c0", "sort": 400},
    {"name": "9. Закрыт — отказ/проигрыш", "color": "#ff8f92", "sort": 300},
    {"name": "10. Готов к архивации",      "color": "#f3beff", "sort": 200},
]

ALLOWED_COLORS = {
    "#fffeb2", "#ffce5a", "#ff8f92", "#ff5e5e",
    "#f3beff", "#ccc8f9", "#98cbff", "#d6eaff",
    "#87f2c0", "#deff81", "#c1e0ff", "#ffdc7f",
}


def api_request(method, url, json_data=None, max_retries=5):
    """Универсальная обёртка с rate-limiting и retry при 429."""
    for attempt in range(max_retries):
        try:
            r = requests.request(
                method, url,
                headers=HEADERS,
                json=json_data,
                timeout=30
            )
            time.sleep(RATE_DELAY)

            if r.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"    ⚠ HTTP 429 (rate limit), жду {wait}с...")
                time.sleep(wait)
                continue

            return r

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            wait = 5 * (attempt + 1)
            print(f"    ⚠ Сетевая ошибка: {type(e).__name__}, жду {wait}с (попытка {attempt+1}/{max_retries})...")
            time.sleep(wait)

    return None


def get_statuses():
    r = api_request("GET", f"https://{DOMAIN}/api/v4/leads/pipelines/{PIPELINE_ID}")
    if r and r.status_code == 200:
        return r.json().get("_embedded", {}).get("statuses", [])
    raise RuntimeError(f"Не удалось получить статусы: {r.status_code if r else 'нет ответа'}")


def delete_status(sid):
    r = api_request("DELETE", f"https://{DOMAIN}/api/v4/leads/pipelines/{PIPELINE_ID}/statuses/{sid}")
    if r:
        if r.status_code == 204:
            return True
        print(f"    (HTTP {r.status_code}: {r.text[:100]})")
    return False


def create_status(name, color, sort):
    payload = {"name": name, "sort": sort}
    if color and color in ALLOWED_COLORS:
        payload["color"] = color

    r = api_request("POST", f"https://{DOMAIN}/api/v4/leads/pipelines/{PIPELINE_ID}/statuses", payload)
    if not r:
        print(f"    (нет ответа от API)")
        return None

    if r.status_code == 200:
        data = r.json()
        created = data.get("_embedded", {}).get("statuses", [{}])[0]
        sid = created.get("id")

        # Если нужен цвет — PATCH с полным набором полей (name + color + sort)
        if color and color in ALLOWED_COLORS and sid:
            rp = api_request(
                "PATCH",
                f"https://{DOMAIN}/api/v4/leads/pipelines/{PIPELINE_ID}/statuses/{sid}",
                {"id": sid, "name": name, "color": color, "sort": sort}
            )
            if rp and rp.status_code not in (200, 204):
                print(f"    (PATCH цвета: HTTP {rp.status_code})")
        return sid
    else:
        print(f"    (HTTP {r.status_code}: {r.text[:200]})")
        return None


def main():
    print("=" * 60)
    if DRY_RUN:
        print("DRY-RUN — план изменений (реальных запросов нет)")
    else:
        print("RETEK amoCRM — Полная пересборка статусов воронки")
        print(f"Rate limit: 1 запрос / {RATE_DELAY}с")
    print("=" * 60)

    current = get_statuses()
    to_delete = [s for s in current if s["id"] not in SYSTEM_IDS]

    print(f"\nТекущих статусов: {len(current)}")
    print(f"Будет удалено: {len(to_delete)} (кроме системных)")
    for s in sorted(to_delete, key=lambda x: x["sort"]):
        print(f"  - [{s['id']}] '{s['name']}' sort={s['sort']}")

    print(f"\nБудет создано: {len(STATUSES)} статусов:")
    for s in STATUSES:
        color_str = s['color'] if s['color'] else "дефолтный"
        print(f"  + '{s['name']}' sort={s['sort']} color={color_str}")

    if DRY_RUN:
        print("\nЗапустите без --dry-run чтобы применить.")
        return

    # Шаг 1: удаляем (кроме «Неразобранное» — системный, не удаляется)
    print(f"\n[1/3] Удаляю {len(to_delete)} статусов...")
    for s in to_delete:
        ok = delete_status(s["id"])
        mark = "✓" if ok else "✗ (системный?)"
        print(f"  {mark} [{s['id']}] '{s['name']}'")

    # Шаг 2: создаём
    print(f"\n[2/3] Создаю {len(STATUSES)} статусов...")
    created_count = 0
    for s in STATUSES:
        sid = create_status(s["name"], s["color"], s["sort"])
        if sid:
            print(f"  ✓ [{sid}] '{s['name']}' sort={s['sort']}")
            created_count += 1
        else:
            print(f"  ✗ Ошибка создания '{s['name']}'")

    # Шаг 3: финальная проверка
    print(f"\n[3/3] Финальный порядок в Канбан (слева→справа):")
    final = get_statuses()
    for i, s in enumerate(sorted(final, key=lambda x: x["sort"], reverse=True), 1):
        marker = " [сист.]" if s["id"] in SYSTEM_IDS else ""
        print(f"  {i:>2}. '{s['name']}'{marker}  sort={s['sort']}")

    print(f"\n{'=' * 60}")
    print(f"Создано {created_count}/{len(STATUSES)} статусов.")
    if created_count == len(STATUSES):
        print("✅ Всё успешно! Обновите страницу amoCRM.")
    else:
        print("⚠ Не все статусы созданы — запустите скрипт повторно.")
    print("=" * 60)


if __name__ == "__main__":
    main()
