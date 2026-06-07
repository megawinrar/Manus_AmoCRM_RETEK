"""
invert_sort.py — Инвертирует sort чтобы «1. Новый тендер» был слева в Канбан.

amoCRM: больший sort = левее.
Текущий: sort 110 (1. Новый тендер) → 20 (10. Готов к архивации)
         → 1. Новый тендер справа (sort=110 < системных)
         
Нужно: 1. Новый тендер sort=1100 (самый большой = самый левый)
       10. Готов к архивации sort=200 (самый маленький = самый правый)

PATCH передаёт name + color + sort — чтобы ничего не сбросилось.
Rate limit: 1.5с между запросами.
"""
import os, time, requests
from dotenv import load_dotenv

load_dotenv()

DOMAIN  = os.getenv("AMO_DOMAIN")
TOKEN   = os.getenv("AMO_ACCESS_TOKEN")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
PIPELINE_ID = 10984442

# id, name, color, NEW sort (больше = левее)
PATCHES = [
    (86357354, "1. Новый тендер",            "#fffeb2", 1100),
    (86357358, "2. Квалификация",            "#fffeb2", 1000),
    (86357362, "3. Расчёт стоимости",        "#ffce5a",  900),
    (86357366, "4. Решение принято",         "#d6eaff",  800),
    (86357370, "5. Подача заявки",           "#98cbff",  700),
    (86357374, "6. Ожидание результата",     "#ccc8f9",  600),
    (86357378, "7. Победа — оформление",     "#deff81",  500),
    (86357382, "8. Поставка / Исполнение",   "#87f2c0",  400),
    (86357386, "9. Закрыт — отказ/проигрыш", "#ff8f92",  300),
    (86357390, "10. Готов к архивации",      "#f3beff",  200),
]

print("Инвертирую sort (1. Новый тендер → слева)...")
print(f"Rate limit: 1.5с между запросами\n")

success = 0
for sid, name, color, new_sort in PATCHES:
    payload = {"id": sid, "name": name, "color": color, "sort": new_sort}
    try:
        r = requests.patch(
            f"https://{DOMAIN}/api/v4/leads/pipelines/{PIPELINE_ID}/statuses/{sid}",
            headers=HEADERS, json=payload, timeout=30
        )
        time.sleep(1.5)
        if r.status_code in (200, 204):
            print(f"  ✓ '{name}' → sort={new_sort}")
            success += 1
        elif r.status_code == 429:
            print(f"  ⚠ 429 rate limit, жду 5с...")
            time.sleep(5)
            r = requests.patch(
                f"https://{DOMAIN}/api/v4/leads/pipelines/{PIPELINE_ID}/statuses/{sid}",
                headers=HEADERS, json=payload, timeout=30
            )
            time.sleep(1.5)
            if r.status_code in (200, 204):
                print(f"  ✓ '{name}' → sort={new_sort} (retry)")
                success += 1
            else:
                print(f"  ✗ '{name}' — HTTP {r.status_code}")
        else:
            print(f"  ✗ '{name}' — HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  ✗ '{name}' — {type(e).__name__}: {e}")

print(f"\nГотово: {success}/{len(PATCHES)}")
if success == len(PATCHES):
    print("✅ Обновите страницу amoCRM — порядок исправлен!")
