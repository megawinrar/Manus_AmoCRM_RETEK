"""
Одноразовый скрипт: исправить карточку 3156121.
Эмулирует post_create_hook для уже существующей сделки:
- Эскалация Р2 → Р1 (дедлайн 10.06.2026 — завтра)
- Переименование: "🔴 СРОЧНО — НПО Высокоточные — 10.06"
- Статусная заметка: PURCHASING (📦 В закупке...)
- Красная заметка: АВТОЭСКАЛАЦИЯ
- Задача: 2 часа (Р1)
"""

import os
import sys
import time
import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from src.microservice.config import (
    auto_escalate_priority,
    build_lead_name,
    PRIORITY_ENUM_IDS,
    PRIORITY_LABELS,
    ESCALATION_NOTE_TEMPLATE,
    STATUS_NOTE_TEMPLATES,
    STATUS_TASK_RULES,
)

# Конфигурация
AMO_DOMAIN = os.getenv("AMO_DOMAIN")
AMO_TOKEN = os.getenv("AMO_ACCESS_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {AMO_TOKEN}",
    "Content-Type": "application/json",
}
BASE_URL = f"https://{AMO_DOMAIN}/api/v4"

LEAD_ID = 3156121
FIELD_PRIORITY = int(os.getenv("FIELD_PRIORITY"))
USER_EMPLOYEE_3 = int(os.getenv("USER_EMPLOYEE_3"))

# Данные сделки
CUSTOMER = "АО «НПО «Высокоточные комплексы»"
DEADLINE = "2026-06-10"
CURRENT_PRIORITY = "Р2"
STATUS_KEY = "PURCHASING"


def main():
    print("=" * 60)
    print(f"ИСПРАВЛЕНИЕ КАРТОЧКИ ID={LEAD_ID}")
    print("=" * 60)

    # 1. Автоэскалация
    print("\n[1/5] Автоэскалация приоритета...")
    new_priority, escalated, reason = auto_escalate_priority(CURRENT_PRIORITY, DEADLINE)
    print(f"  Результат: {CURRENT_PRIORITY} → {new_priority} (escalated={escalated})")
    print(f"  Причина: {reason}")

    if not escalated:
        print("  ⚠ Эскалация не сработала — проверьте дату!")
        # Всё равно ставим Р1 вручную
        new_priority = "Р1"
        reason = f"дедлайн {DEADLINE} — менее 48ч, ручная эскалация"
        print(f"  → Принудительно: {new_priority}")

    priority_enum_id = PRIORITY_ENUM_IDS[new_priority]

    # PATCH приоритет
    patch = [{"id": LEAD_ID, "custom_fields_values": [
        {"field_id": FIELD_PRIORITY, "values": [{"enum_id": priority_enum_id}]}
    ]}]
    resp = requests.patch(f"{BASE_URL}/leads", json=patch, headers=HEADERS)
    print(f"  PATCH приоритет: {resp.status_code}")
    time.sleep(0.5)

    # 2. Переименование
    print("\n[2/5] Переименование карточки...")
    customer_clean = "НПО Высокоточные комп"
    deadline_display = "10.06"
    lead_name = build_lead_name(priority_enum_id, customer_clean, deadline_display)
    print(f"  Новое название: \"{lead_name}\"")

    patch = [{"id": LEAD_ID, "name": lead_name}]
    resp = requests.patch(f"{BASE_URL}/leads", json=patch, headers=HEADERS)
    print(f"  PATCH название: {resp.status_code}")
    time.sleep(0.5)

    # 3. Статусная заметка
    print("\n[3/5] Статусная заметка (PURCHASING)...")
    status_note = STATUS_NOTE_TEMPLATES[STATUS_KEY]
    payload = [{"note_type": "common", "params": {"text": status_note}, "entity_id": LEAD_ID}]
    resp = requests.post(f"{BASE_URL}/leads/{LEAD_ID}/notes", json=payload, headers=HEADERS)
    print(f"  POST заметка: {resp.status_code}")
    preview = status_note[:44]
    print(f"  Канбан-превью: \"{preview}\"")
    time.sleep(0.5)

    # 4. Красная заметка (эскалация)
    print("\n[4/5] Красная заметка (АВТОЭСКАЛАЦИЯ)...")
    escalation_note = ESCALATION_NOTE_TEMPLATE.format(
        old_priority=CURRENT_PRIORITY,
        new_priority=new_priority,
        reason=reason,
        deadline=DEADLINE,
    )
    payload = [{"note_type": "common", "params": {"text": escalation_note}, "entity_id": LEAD_ID}]
    resp = requests.post(f"{BASE_URL}/leads/{LEAD_ID}/notes", json=payload, headers=HEADERS)
    print(f"  POST красная заметка: {resp.status_code}")
    time.sleep(0.5)

    # 5. Задача (2 часа для Р1)
    print("\n[5/5] Задача (2 часа — Р1)...")
    task_rule = STATUS_TASK_RULES[STATUS_KEY]
    task_text = f"🔴 СРОЧНО! {task_rule['text']}\n\n⏰ Дедлайн подачи: {DEADLINE}"
    task_deadline = int((datetime.now() + timedelta(hours=2)).timestamp())

    task_payload = [{
        "text": task_text,
        "complete_till": task_deadline,
        "responsible_user_id": USER_EMPLOYEE_3,
        "entity_id": LEAD_ID,
        "entity_type": "leads",
        "task_type_id": task_rule.get("task_type_id", 1),
    }]
    resp = requests.post(f"{BASE_URL}/tasks", json=task_payload, headers=HEADERS)
    if resp.status_code in (200, 201):
        task_id = resp.json()["_embedded"]["tasks"][0]["id"]
        print(f"  Задача создана: ID={task_id} (дедлайн: 2ч)")
    else:
        print(f"  ОШИБКА: {resp.status_code} {resp.text}")

    # Итог
    print("\n" + "=" * 60)
    print("ГОТОВО!")
    print(f"  Сделка: https://{AMO_DOMAIN}/leads/detail/{LEAD_ID}")
    print(f"  Название: \"{lead_name}\"")
    print(f"  Приоритет: 🔴 {new_priority}")
    print(f"  Статусная заметка: ✓")
    print(f"  Красная заметка: ✓")
    print(f"  Задача (2ч): ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
