"""
patch_colors.py — Применяет цвета к созданным статусам.
Rate limit: 1 запрос / 1.5с (лимит amoCRM: 7 req/s на интеграцию)
"""
import os, time, requests
from dotenv import load_dotenv

load_dotenv()

DOMAIN  = os.getenv("AMO_DOMAIN")
TOKEN   = os.getenv("AMO_ACCESS_TOKEN")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
PIPELINE_ID = 10984442

# ID статусов из только что созданных + целевые цвета
# sort назначен amoCRM автоматически: 110,100,90...20 — порядок уже правильный
PATCHES = [
    # id,         name,                          color (None = оставить дефолт)
    (86357354, "1. Новый тендер",            None),        # дефолтный жёлтый — ок
    (86357358, "2. Квалификация",            "#fffeb2"),   # светло-жёлтый
    (86357362, "3. Расчёт стоимости",        "#ffce5a"),   # оранжевый
    (86357366, "4. Решение принято",         "#d6eaff"),   # голубой
    (86357370, "5. Подача заявки",           "#98cbff"),   # синий
    (86357374, "6. Ожидание результата",     "#ccc8f9"),   # индиго
    (86357378, "7. Победа — оформление",     "#deff81"),   # зелёный
    (86357382, "8. Поставка / Исполнение",   "#87f2c0"),   # мятный
    (86357386, "9. Закрыт — отказ/проигрыш", "#ff8f92"),   # красный
    (86357390, "10. Готов к архивации",      "#f3beff"),   # фиолетовый
]

print("Применяю цвета к статусам...")
print(f"Rate limit: 1.5с между запросами\n")

success = 0
for sid, name, color in PATCHES:
    if color is None:
        print(f"  = [{sid}] '{name}' — цвет дефолтный, пропускаю")
        success += 1
        continue

    payload = {"id": sid, "name": name, "color": color}
    try:
        r = requests.patch(
            f"https://{DOMAIN}/api/v4/leads/pipelines/{PIPELINE_ID}/statuses/{sid}",
            headers=HEADERS, json=payload, timeout=30
        )
        time.sleep(1.5)
        if r.status_code in (200, 204):
            print(f"  ✓ [{sid}] '{name}' → {color}")
            success += 1
        elif r.status_code == 429:
            print(f"  ⚠ [{sid}] '{name}' — 429 rate limit, жду 5с...")
            time.sleep(5)
            r = requests.patch(
                f"https://{DOMAIN}/api/v4/leads/pipelines/{PIPELINE_ID}/statuses/{sid}",
                headers=HEADERS, json=payload, timeout=30
            )
            if r.status_code in (200, 204):
                print(f"  ✓ [{sid}] '{name}' → {color} (retry)")
                success += 1
            else:
                print(f"  ✗ [{sid}] '{name}' — HTTP {r.status_code}")
        else:
            print(f"  ✗ [{sid}] '{name}' — HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"  ✗ [{sid}] '{name}' — {type(e).__name__}: {e}")

print(f"\nГотово: {success}/{len(PATCHES)} статусов обновлены.")
