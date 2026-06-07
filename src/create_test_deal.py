"""
Скрипт для создания тестовой сделки в amoCRM на основе реального тендера.
Имитирует работу LLM-классификатора.
"""
import os
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DOMAIN = os.getenv("AMO_DOMAIN")
TOKEN = os.getenv("AMO_ACCESS_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}
BASE = f"https://{DOMAIN}"


def ts(dt_str: str) -> int:
    """Convert YYYY-MM-DD to unix timestamp (Moscow time = UTC+3)."""
    dt = datetime.strptime(dt_str, "%Y-%m-%d").replace(
        hour=16, minute=0, tzinfo=timezone.utc
    )
    return int(dt.timestamp()) - 3 * 3600  # subtract 3h to get MSK 16:00


def create_deal(deal_data: dict) -> dict:
    url = f"{BASE}/api/v4/leads"
    resp = requests.post(url, headers=HEADERS, json=[deal_data])
    resp.raise_for_status()
    return resp.json()


def create_task(lead_id: int, task_data: dict) -> dict:
    url = f"{BASE}/api/v4/tasks"
    task_data["entity_id"] = lead_id
    task_data["entity_type"] = "leads"
    resp = requests.post(url, headers=HEADERS, json=[task_data])
    resp.raise_for_status()
    return resp.json()


def add_note(lead_id: int, text: str) -> dict:
    url = f"{BASE}/api/v4/leads/{lead_id}/notes"
    resp = requests.post(url, headers=HEADERS, json=[{
        "note_type": "common",
        "params": {"text": text}
    }])
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# ТЕНДЕР 1: 0201-2026-02391 Поставка фрез — КБП Шипунова
# Классификация LLM:
#   type_situation: Запрос котировок / реальные торги
#   priority: Р1 — Срочно (срок подачи 08.06.2026 — через 2 дня!)
#   direction: HSS-STANDARD (фрезы ZPS-FN HSSE-PM — стандартный быстрорез)
#   responsible: Сотрудник 3 (закупщик)
#   status: Передано в закупку / расчёт
# ─────────────────────────────────────────────────────────────────────────────

PIPELINE_ACTIVE = int(os.getenv("AMO_PIPELINE_ACTIVE_ID"))
STATUS_PURCHASING = int(os.getenv("STATUS_5_PURCHASING"))
USER_EMPLOYEE_3 = int(os.getenv("USER_EMPLOYEE_3"))
USER_EMPLOYEE_2 = int(os.getenv("USER_EMPLOYEE_2"))

# Field IDs
F = {
    "external_id":      int(os.getenv("FIELD_EXTERNAL_ID")),
    "source":           int(os.getenv("FIELD_SOURCE")),
    "platform_url":     int(os.getenv("FIELD_PLATFORM_URL")),
    "customer":         int(os.getenv("FIELD_CUSTOMER")),
    "procedure_num":    int(os.getenv("FIELD_PROCEDURE_NUM")),
    "situation_type":   int(os.getenv("FIELD_SITUATION_TYPE")),
    "procedure_type":   int(os.getenv("FIELD_PROCEDURE_TYPE")),
    "priority":         int(os.getenv("FIELD_PRIORITY")),
    "direction":        int(os.getenv("FIELD_DIRECTION")),
    "direction_subtype":int(os.getenv("FIELD_DIRECTION_SUBTYPE")),
    "nmc":              int(os.getenv("FIELD_NMC")),
    "deadline":         int(os.getenv("FIELD_DEADLINE")),
    "next_action":      int(os.getenv("FIELD_NEXT_ACTION")),
    "next_action_date": int(os.getenv("FIELD_NEXT_ACTION_DATE")),
    "resp_sales":       int(os.getenv("FIELD_RESP_SALES")),
    "resp_purchase":    int(os.getenv("FIELD_RESP_PURCHASE")),
    "needs_purchase":   int(os.getenv("FIELD_NEEDS_PURCHASE")),
    "archive_llm":      int(os.getenv("FIELD_ARCHIVE_LLM")),
    "llm_confidence":   int(os.getenv("FIELD_LLM_CONFIDENCE")),
    "llm_comment":      int(os.getenv("FIELD_LLM_COMMENT")),
}

deadline_ts = ts("2026-06-08")
next_action_ts = ts("2026-06-07")  # завтра — срочно!

deal = {
    "name": "[Р1] Запрос котировок — КБП Шипунова — фрезы ZPS-FN HSSE-PM — срок 08.06",
    "pipeline_id": PIPELINE_ACTIVE,
    "status_id": STATUS_PURCHASING,
    "responsible_user_id": USER_EMPLOYEE_3,
    "price": 19139188,
    "custom_fields_values": [
        {"field_id": F["external_id"],      "values": [{"value": "0201-2026-02391"}]},
        {"field_id": F["source"],           "values": [{"enum_id": 215645}]},  # Тендерная площадка
        {"field_id": F["platform_url"],     "values": [{"value": "https://sfilee223.etprf.ru/?path=sfilee223/2026/06/02/I1129783-5a63-40ca-b293-f4aa19b4f568.83307FDC4D249A23A62B81F0C18D9E37.html"}]},
        {"field_id": F["customer"],         "values": [{"value": "АО КБП им. академика А.Г. Шипунова"}]},
        {"field_id": F["procedure_num"],    "values": [{"value": "SP26052500177 / 0201-2026-02391"}]},
        {"field_id": F["situation_type"],   "values": [{"enum_id": 215657}]},  # Запрос котировок / реальные торги
        {"field_id": F["procedure_type"],   "values": [{"enum_id": 215663}]},  # Запрос котировок
        {"field_id": F["priority"],         "values": [{"enum_id": 215673}]},  # Р1 — Срочно
        {"field_id": F["direction"],        "values": [{"enum_id": 215683}]},  # HSS-STANDARD — стандартный быстрорез / ГОСТ
        # direction_subtype: есть только для специнструмента, не заполняем для стандартного
        {"field_id": F["nmc"],              "values": [{"value": 19139188}]},
        {"field_id": F["deadline"],         "values": [{"value": deadline_ts}]},
        {"field_id": F["next_action"],      "values": [{"value": "Срочно! Сделать расчёт и КП по 11+ позициям фрез ZPS-FN HSSE-PM (серии 121517, 125517), срок подачи 08.06.2026 16:00"}]},
        {"field_id": F["next_action_date"], "values": [{"value": next_action_ts}]},
        {"field_id": F["resp_sales"],       "values": [{"value": "Сотрудник 2"}]},
        {"field_id": F["resp_purchase"],    "values": [{"value": "Сотрудник 3"}]},
        {"field_id": F["needs_purchase"],   "values": [{"value": True}]},  # checkbox: bool
        {"field_id": F["archive_llm"],      "values": [{"value": "Архив — направления / HSS ГОСТ"}]},
        {"field_id": F["llm_confidence"],   "values": [{"value": "0.95"}]},
        {"field_id": F["llm_comment"],      "values": [{"value": "Закрытый запрос котировок на поставку 11 позиций концевых фрез ZPS-FN HSSE-PM (серии 121517, 125517). Заказчик — АО КБП Шипунова (ОПК, Тула). НМЦ ~19.1 млн руб. Срок подачи 08.06.2026 — СРОЧНО (2 дня). Допускается эквивалент. Стандартный каталожный инструмент, не спецзаказ по чертежам. Направление: HSS-STANDARD."}]},
    ]
}

print("Создаю сделку в amoCRM...")
print(f"Название: {deal['name']}")
print(f"Статус: Передано в закупку / расчёт (ID: {STATUS_PURCHASING})")
print(f"НМЦ: 19 139 188 руб.")
print()

result = create_deal(deal)
lead_id = result["_embedded"]["leads"][0]["id"]
print(f"✅ Сделка создана! ID: {lead_id}")
print(f"   Ссылка: https://{DOMAIN}/leads/detail/{lead_id}")
print()

# Создаём задачу: срочный расчёт
print("Создаю задачу...")
task_result = create_task(lead_id, {
    "task_type_id": 2,  # Написать / Рассчитать
    "text": "🔴 СРОЧНО! Сделать расчёт и КП по 11 позициям фрез ZPS-FN HSSE-PM (серии 121517, 125517). Срок подачи заявки: 08.06.2026 16:00. Заказчик: АО КБП Шипунова (Тула). НМЦ: 19.1 млн руб. Допускается эквивалент.",
    "complete_till": next_action_ts,
    "responsible_user_id": USER_EMPLOYEE_3,
})
task_id = task_result["_embedded"]["tasks"][0]["id"]
print(f"✅ Задача создана! ID: {task_id}")
print()

# Добавляем примечание с деталями
print("Добавляю примечание с деталями тендера...")
note_text = """📋 ТЕНДЕР: 0201-2026-02391 Поставка фрез
Организатор: АО НПО "Высокоточные комплексы" (d.gayday@npovk.ru, Гайдай Дарья Михайловна)
Заказчик: АО КБП им. академика А.Г. Шипунова, г. Тула

⏰ СРОК ПОДАЧИ: 08.06.2026, 16:00 МСК
📅 Рассмотрение заявок: 17.06.2026
📅 Подведение итогов: 22.06.2026

💰 НМЦ: 19 139 188,29 руб.
🔒 Обеспечение заявки: 95 695,94 руб.
📦 Место поставки: 300004, Тульская обл., г. Тула, ул. Щегловская Засека, д. 31Б

📌 ПОЗИЦИИ (11 шт, все — фрезы ZPS-FN HSSE-PM, покрытие AlTiN):
1. 120518.130 HSSCo8 — 6 шт — 20 406 руб.
2. 121517.060 HSSE-PM — 70 шт — 269 011 руб.
3. 121517.080 HSSE-PM — 70 шт — 335 509 руб.
4. 121517.100 HSSE-PM — 70 шт — 397 294 руб.
5. 121517.120 HSSE-PM — 60 шт — 406 832 руб.
6. 121517.140 HSSE-PM — 50 шт — 394 780 руб.
7. 121517.160 HSSE-PM — 70 шт — 654 660 руб.
8. 121517.180 HSSE-PM — 60 шт — 683 057 руб.
9. 121517.160 HSSE-PM — 70 шт — 904 291 руб.
10. 125517.200 HSSE-PM — 60 шт — 1 129 589 руб.
11. 125517.320 HSSE-PM — 20 шт — 869 188 руб.

✅ Допускается эквивалент
⚠️ Запрет иностранных товаров (кроме разрешённых исключений)
🛡️ Закупка для обеспечения обороны страны"""

note_result = add_note(lead_id, note_text)
print(f"✅ Примечание добавлено!")
print()
print("=" * 60)
print(f"ИТОГ: Сделка #{lead_id} создана в amoCRM")
print(f"Ссылка: https://{DOMAIN}/leads/detail/{lead_id}")
