"""
Обогащение сделки 3153625: пометить как дубль → перенести в архив (дубли).
Основная карточка: 3156121.
"""
import os
import sys
import requests
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

AMO_DOMAIN = os.getenv("AMO_DOMAIN")
AMO_TOKEN = os.getenv("AMO_ACCESS_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {AMO_TOKEN}",
    "Content-Type": "application/json",
}
BASE_URL = f"https://{AMO_DOMAIN}/api/v4"

# Архивная воронка — Направления, статус "Дубли"
PIPELINE_ARCHIVE_DIRECTIONS = int(os.getenv("AMO_PIPELINE_ARCHIVE_DIRECTIONS_ID"))
ARCH_DIR_DUPL = int(os.getenv("ARCH_DIR_DUPL"))

LEAD_DUPLICATE = 3153625
LEAD_MAIN = 3156121


def main():
    print("=" * 60)
    print("ОБОГАЩЕНИЕ ДУБЛЯ: сделка 3153625 → архив (дубли)")
    print("=" * 60)

    # 1. Добавляем заметку
    print("\n[1] Добавляю заметку о дубле...")
    note_text = (
        f"⚠️ ДУБЛЬ — основная карточка: #{LEAD_MAIN}\n\n"
        f"Эта сделка является дублем. Основная (актуальная) карточка:\n"
        f"https://{AMO_DOMAIN}/leads/detail/{LEAD_MAIN}\n\n"
        f"Причина: при ручной эмуляции LLM-классификатора не была выполнена "
        f"проверка на дубли. Исправлено — добавлена 3-уровневая дедупликация.\n\n"
        f"Перенесено в архив (дубли): {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    payload = [{"note_type": "common", "params": {"text": note_text}, "entity_id": LEAD_DUPLICATE}]
    resp = requests.post(f"{BASE_URL}/leads/{LEAD_DUPLICATE}/notes", json=payload, headers=HEADERS)
    if resp.status_code in (200, 201):
        print(f"  Заметка добавлена ✓")
    else:
        print(f"  ОШИБКА: {resp.status_code} {resp.text}")

    # 2. Переносим в архивную воронку (статус "Дубли")
    print("\n[2] Переношу в архив (воронка Направления → статус Дубли)...")
    patch_payload = [
        {
            "id": LEAD_DUPLICATE,
            "pipeline_id": PIPELINE_ARCHIVE_DIRECTIONS,
            "status_id": ARCH_DIR_DUPL,
            "custom_fields_values": [
                {
                    "field_id": int(os.getenv("FIELD_ARCHIVE_LLM")),
                    "values": [{"enum_id": 215771}]  # Архив — направления / Дубли / мусор
                },
                {
                    "field_id": int(os.getenv("FIELD_CLOSE_REASON")),
                    "values": [{"enum_id": 215757}]  # Дубль
                },
            ]
        }
    ]
    resp = requests.patch(f"{BASE_URL}/leads", json=patch_payload, headers=HEADERS)
    if resp.status_code in (200, 201):
        print(f"  Сделка перенесена в архив ✓")
        print(f"  Воронка: Архив — Направления (ID={PIPELINE_ARCHIVE_DIRECTIONS})")
        print(f"  Статус: Дубли (ID={ARCH_DIR_DUPL})")
    else:
        print(f"  ОШИБКА: {resp.status_code} {resp.text}")

    # 3. Также добавим заметку к основной карточке
    print("\n[3] Добавляю заметку к основной карточке 3156121...")
    note_main = (
        f"📎 Обнаружен и обработан дубль: #{LEAD_DUPLICATE}\n\n"
        f"Дубль перенесён в архив (воронка Направления → Дубли).\n"
        f"Эта карточка является основной.\n\n"
        f"Дедупликация: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    payload = [{"note_type": "common", "params": {"text": note_main}, "entity_id": LEAD_MAIN}]
    resp = requests.post(f"{BASE_URL}/leads/{LEAD_MAIN}/notes", json=payload, headers=HEADERS)
    if resp.status_code in (200, 201):
        print(f"  Заметка к основной карточке добавлена ✓")
    else:
        print(f"  ОШИБКА: {resp.status_code} {resp.text}")

    print("\n" + "=" * 60)
    print("ГОТОВО!")
    print(f"  Дубль #{LEAD_DUPLICATE} → архив (дубли)")
    print(f"  Основная #{LEAD_MAIN} → без изменений, заметка добавлена")
    print("=" * 60)


if __name__ == "__main__":
    main()
