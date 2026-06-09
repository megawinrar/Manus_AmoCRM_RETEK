"""
Эмуляция LLM-классификатора: создание сделки в amoCRM.

Тендер: Gesac - 86 поз.
Заказчик: АО «КБП» (Ростех)
НМЦ: 6 719 075,91 руб.
Направление: CARBIDE-STANDARD (твердосплав стандартный)
Приоритет: Р2 (Быстрые деньги)
Тип ситуации: Запрос котировок / реальные торги
Маршрутизация: → Статус 5 (Передано в закупку) → Сотрудник 3
"""

import os
import sys
import time
import requests
from datetime import datetime, timedelta

# Загружаем .env
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ═══════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════

AMO_DOMAIN = os.getenv("AMO_DOMAIN")
AMO_TOKEN = os.getenv("AMO_ACCESS_TOKEN")
PIPELINE_ID = int(os.getenv("AMO_PIPELINE_ACTIVE_ID"))

# Статус: 5. Передано в закупку (по маршрутизации Р2 + реальные торги)
TARGET_STATUS_ID = int(os.getenv("STATUS_5_PURCHASING"))

# Ответственный: Сотрудник 3 (закупщик)
RESPONSIBLE_USER_ID = int(os.getenv("USER_EMPLOYEE_3"))

# Кастомные поля
FIELDS = {
    "CUSTOMER": int(os.getenv("FIELD_CUSTOMER")),
    "SITUATION_TYPE": int(os.getenv("FIELD_SITUATION_TYPE")),
    "PRIORITY": int(os.getenv("FIELD_PRIORITY")),
    "DIRECTION": int(os.getenv("FIELD_DIRECTION")),
    "NMC": int(os.getenv("FIELD_NMC")),
    "DEADLINE": int(os.getenv("FIELD_DEADLINE")),
    "SOURCE": int(os.getenv("FIELD_SOURCE")),
    "LLM_CONFIDENCE": int(os.getenv("FIELD_LLM_CONFIDENCE")),
    "LLM_COMMENT": int(os.getenv("FIELD_LLM_COMMENT")),
    "PROCEDURE_TYPE": int(os.getenv("FIELD_PROCEDURE_TYPE")),
}

# ═══════════════════════════════════════════════════════════════
# ДАННЫЕ ТЕНДЕРА (результат LLM-классификации)
# ═══════════════════════════════════════════════════════════════

LLM_RESULT = {
    "priority": "Р2",
    "situation_type": "Запрос котировок / реальные торги",
    "direction": "CARBIDE-STANDARD",
    "sub_direction": None,
    "customer": "АО «КБП» (Ростех)",
    "product_description": "Поставка твердосплавного инструмента Gesac: 86 позиций — свёрла, фрезы, пластины. НМЦ 6 719 075,91 руб.",
    "confidence": 0.95,
    "comment": "Закрытый запрос котировок от КБП (Ростех). 86 позиций стандартного твердосплава Gesac. Сумма ~6.7 млн руб. Срок поставки 90 дней."
}

# Название сделки: Приоритет / Заказчик / Дедлайн
DEAL_NAME = f"Р2 / КБП (Ростех) / Gesac 86 поз. / 6.7 млн"

# ═══════════════════════════════════════════════════════════════
# API ВЫЗОВЫ
# ═══════════════════════════════════════════════════════════════

HEADERS = {
    "Authorization": f"Bearer {AMO_TOKEN}",
    "Content-Type": "application/json",
}
BASE_URL = f"https://{AMO_DOMAIN}/api/v4"


def create_lead():
    """Создать сделку в amoCRM."""
    # Дедлайн: 90 дней с момента заключения договора (из ТЗ)
    deadline_date = datetime.now() + timedelta(days=90)
    deadline_ts = int(deadline_date.timestamp())

    payload = [
        {
            "name": DEAL_NAME,
            "pipeline_id": PIPELINE_ID,
            "status_id": TARGET_STATUS_ID,
            "responsible_user_id": RESPONSIBLE_USER_ID,
            "price": 6719076,  # НМЦ в рублях (целое)
            "custom_fields_values": [
                {"field_id": FIELDS["CUSTOMER"], "values": [{"value": LLM_RESULT["customer"]}]},
                {"field_id": FIELDS["SITUATION_TYPE"], "values": [{"enum_id": 215657}]},  # Запрос котировок / реальные торги
                {"field_id": FIELDS["PRIORITY"], "values": [{"enum_id": 215675}]},  # Р2 — Быстрые Деньги
                {"field_id": FIELDS["DIRECTION"], "values": [{"enum_id": 215685}]},  # CARBIDE-STANDARD — стандартный твердосплав
                {"field_id": FIELDS["NMC"], "values": [{"value": 6719075.91}]},
                {"field_id": FIELDS["DEADLINE"], "values": [{"value": deadline_ts}]},
                {"field_id": FIELDS["SOURCE"], "values": [{"enum_id": 215653}]},  # Другое (Яндекс.Диск / LLM)
                {"field_id": FIELDS["LLM_CONFIDENCE"], "values": [{"value": 0.95}]},
                {"field_id": FIELDS["LLM_COMMENT"], "values": [{"value": LLM_RESULT["comment"]}]},
                {"field_id": FIELDS["PROCEDURE_TYPE"], "values": [{"enum_id": 215663}]},  # Запрос котировок
            ],
        }
    ]

    resp = requests.post(f"{BASE_URL}/leads", json=payload, headers=HEADERS)
    print(f"[CREATE LEAD] Status: {resp.status_code}")

    if resp.status_code in (200, 201):
        data = resp.json()
        lead_id = data["_embedded"]["leads"][0]["id"]
        print(f"[CREATE LEAD] ✅ Сделка создана: ID={lead_id}")
        print(f"[CREATE LEAD]    Название: {DEAL_NAME}")
        print(f"[CREATE LEAD]    Статус: 5. Передано в закупку (ID={TARGET_STATUS_ID})")
        print(f"[CREATE LEAD]    Ответственный: User ID={RESPONSIBLE_USER_ID}")
        return lead_id
    else:
        print(f"[CREATE LEAD] ❌ Ошибка: {resp.text}")
        return None


def create_task(lead_id):
    """Создать автозадачу для сделки."""
    deadline = int((datetime.now() + timedelta(days=2)).timestamp())

    payload = [
        {
            "text": "Рассчитать себестоимость, подготовить КП. Проверить наличие у поставщиков.\n\n"
                    "📋 Тендер: Gesac 86 позиций (свёрла, фрезы, пластины)\n"
                    "💰 НМЦ: 6 719 075,91 руб.\n"
                    "🏭 Заказчик: АО «КБП» (Ростех)\n"
                    "📅 Срок поставки: 90 дней с момента договора\n"
                    "📁 Файлы: Яндекс.Диск / ТОРГИ / 09.06.2026 / Gesac - 86 поз.",
            "complete_till": deadline,
            "responsible_user_id": RESPONSIBLE_USER_ID,
            "entity_id": lead_id,
            "entity_type": "leads",
            "task_type_id": 1,  # Связаться
        }
    ]

    resp = requests.post(f"{BASE_URL}/tasks", json=payload, headers=HEADERS)
    print(f"[CREATE TASK] Status: {resp.status_code}")

    if resp.status_code in (200, 201):
        data = resp.json()
        task_id = data["_embedded"]["tasks"][0]["id"]
        print(f"[CREATE TASK] ✅ Задача создана: ID={task_id}")
        print(f"[CREATE TASK]    Дедлайн: {datetime.fromtimestamp(deadline).strftime('%d.%m.%Y %H:%M')}")
        return task_id
    else:
        print(f"[CREATE TASK] ❌ Ошибка: {resp.text}")
        return None


def add_note(lead_id):
    """Добавить заметку в ленту сделки."""
    note_text = (
        "🤖 LLM-классификатор (эмуляция)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Приоритет: {LLM_RESULT['priority']}\n"
        f"📁 Направление: {LLM_RESULT['direction']}\n"
        f"🏷️ Тип ситуации: {LLM_RESULT['situation_type']}\n"
        f"🏭 Заказчик: {LLM_RESULT['customer']}\n"
        f"💰 НМЦ: 6 719 075,91 руб.\n"
        f"🎯 Уверенность: {LLM_RESULT['confidence']}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💬 Комментарий: {LLM_RESULT['comment']}\n\n"
        "📂 Источник: Яндекс.Диск / ТОРГИ / 09.06.2026 / Gesac - 86 поз.\n"
        "📄 Файлы: ИоЗ.docx, Приложение №1 (проект договора), "
        "Приложение №3 (обоснование НМЦ), Gesac-86pos_RU.xlsx\n\n"
        "➡️ Маршрутизация: Р2 + Реальные торги → Статус 5 (Передано в закупку)"
    )

    payload = [
        {
            "note_type": "common",
            "params": {"text": note_text},
            "entity_id": lead_id,
        }
    ]

    resp = requests.post(
        f"{BASE_URL}/leads/{lead_id}/notes",
        json=payload,
        headers=HEADERS,
    )
    print(f"[ADD NOTE] Status: {resp.status_code}")

    if resp.status_code in (200, 201):
        print(f"[ADD NOTE] ✅ Заметка добавлена в ленту сделки")
    else:
        print(f"[ADD NOTE] ❌ Ошибка: {resp.text}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 ЭМУЛЯЦИЯ LLM-КЛАССИФИКАТОРА")
    print("=" * 60)
    print(f"\n📂 Тендер: Gesac - 86 поз.")
    print(f"📅 Дата: 09.06.2026")
    print(f"🏭 Заказчик: {LLM_RESULT['customer']}")
    print(f"💰 НМЦ: 6 719 075,91 руб.")
    print(f"📊 Приоритет: {LLM_RESULT['priority']}")
    print(f"📁 Направление: {LLM_RESULT['direction']}")
    print(f"🎯 Уверенность: {LLM_RESULT['confidence']}")
    print(f"\n{'─' * 60}")
    print(f"➡️ Маршрутизация: Статус 5 → Сотрудник 3 (закупщик)")
    print(f"{'─' * 60}\n")

    # 1. Создать сделку
    lead_id = create_lead()
    if not lead_id:
        print("\n❌ Не удалось создать сделку. Прерываю.")
        sys.exit(1)

    time.sleep(1)

    # 2. Создать задачу
    create_task(lead_id)

    time.sleep(1)

    # 3. Добавить заметку
    add_note(lead_id)

    print(f"\n{'=' * 60}")
    print(f"✅ ГОТОВО!")
    print(f"   Сделка: https://{AMO_DOMAIN}/leads/detail/{lead_id}")
    print(f"{'=' * 60}")
