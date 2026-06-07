"""
Перегруппировка полей карточки amoCRM.

Новая логика группировки (сверху вниз):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
БЛОК 1 — КЛАССИФИКАЦИЯ (что за тендер, кто, откуда)
  Приоритет
  Тип ситуации
  Направление
  Подтип направления
  Нужна закупка / расчёт
  Есть сомнения СОЗ или реальные торги

БЛОК 2 — ПРОЦЕСС (движение по воронке)
  Решение дилера          ← остаётся, заполняется на статусе 8
  Дилер / канал продаж
  Производство
  Причина закрытия

БЛОК 3 — ТЕНДЕР (данные тендера)
  Внешний ID заявки
  Источник
  Ссылка на площадку
  Ссылка на папку / документы
  Заказчик
  ИНН
  Номер процедуры
  Тип процедуры
  НМЦ
  Срок подачи

БЛОК 4 — ЗАДАЧА (следующий шаг)
  Следующее действие
  Дата следующего действия
  Ответственный продажник
  Ответственный закупщик
  Команда

БЛОК 5 — АРХИВ (заполняется при закрытии)
  Архивное назначение LLM
  Архивное назначение итоговое
  Дата возврата из архива

БЛОК 6 — LLM (служебное)
  LLM confidence
  LLM comment
  Manager comment

УДАЛИТЬ:
  Статус КП (380333) — дублирует статус воронки
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
DOMAIN = os.getenv("AMO_DOMAIN")
TOKEN = os.getenv("AMO_ACCESS_TOKEN")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Новый порядок: (field_id, sort_value, new_name_if_changed)
# sort: чем меньше — тем выше в карточке
NEW_ORDER = [
    # ── БЛОК 1: КЛАССИФИКАЦИЯ ──────────────────────────────────
    (380309, 100, None),   # Приоритет
    (380305, 110, None),   # Тип ситуации
    (380311, 120, None),   # Направление
    (380313, 130, None),   # Подтип направления
    (380329, 140, None),   # Нужна закупка / расчёт
    (380331, 150, None),   # Есть сомнения СОЗ или реальные торги

    # ── БЛОК 2: ПРОЦЕСС ────────────────────────────────────────
    (380337, 210, None),   # Решение дилера
    (380335, 220, None),   # Дилер / канал продаж
    (380339, 230, None),   # Производство
    (380341, 240, None),   # Причина закрытия

    # ── БЛОК 3: ТЕНДЕР ─────────────────────────────────────────
    (380291, 310, None),   # Внешний ID заявки
    (380293, 320, None),   # Источник
    (380295, 330, None),   # Ссылка на площадку
    (380297, 340, None),   # Ссылка на папку / документы
    (380299, 350, None),   # Заказчик
    (380301, 360, None),   # ИНН
    (380303, 370, None),   # Номер процедуры
    (380307, 380, None),   # Тип процедуры
    (380315, 390, None),   # НМЦ
    (380317, 400, None),   # Срок подачи

    # ── БЛОК 4: ЗАДАЧА ─────────────────────────────────────────
    (380319, 510, None),   # Следующее действие
    (380321, 520, None),   # Дата следующего действия
    (380323, 530, None),   # Ответственный продажник
    (380325, 540, None),   # Ответственный закупщик
    (380327, 550, None),   # Команда

    # ── БЛОК 5: АРХИВ ──────────────────────────────────────────
    (380343, 610, None),   # Архивное назначение LLM
    (380345, 620, None),   # Архивное назначение итоговое
    (380347, 630, None),   # Дата возврата из архива

    # ── БЛОК 6: LLM (служебное) ────────────────────────────────
    (380349, 710, None),   # LLM confidence
    (380351, 720, None),   # LLM comment
    (380353, 730, None),   # Manager comment
]

FIELD_TO_DELETE = 380333  # Статус КП — удаляем


def reorder_fields():
    print("Обновляю порядок полей...")
    updates = []
    for field_id, sort_val, new_name in NEW_ORDER:
        patch = {"id": field_id, "sort": sort_val}
        if new_name:
            patch["name"] = new_name
        updates.append(patch)

    resp = requests.patch(
        f"https://{DOMAIN}/api/v4/leads/custom_fields",
        headers=HEADERS,
        json=updates,
    )
    if resp.status_code in (200, 204):
        print(f"✅ Порядок обновлён для {len(updates)} полей")
    else:
        print(f"❌ Ошибка обновления: {resp.status_code}")
        print(resp.text[:500])


def delete_status_kp():
    print(f"\nУдаляю поле 'Статус КП' (ID: {FIELD_TO_DELETE})...")
    resp = requests.delete(
        f"https://{DOMAIN}/api/v4/leads/custom_fields/{FIELD_TO_DELETE}",
        headers=HEADERS,
    )
    if resp.status_code in (200, 204):
        print(f"✅ Поле 'Статус КП' удалено")
    else:
        print(f"❌ Ошибка удаления: {resp.status_code}")
        print(resp.text[:300])


def verify_order():
    print("\nПроверяю новый порядок...")
    resp = requests.get(
        f"https://{DOMAIN}/api/v4/leads/custom_fields?limit=100",
        headers=HEADERS,
    )
    fields = resp.json().get("_embedded", {}).get("custom_fields", [])
    fields = [f for f in fields if f["id"] >= 380291]
    fields.sort(key=lambda x: x.get("sort", 9999))
    print(f"\n{'Sort':>5}  {'ID':>7}  {'Тип':15}  Название")
    print("─" * 60)
    for f in fields:
        print(f'{f["sort"]:5d}  {f["id"]:7d}  {f["type"]:15s}  {f["name"]}')


if __name__ == "__main__":
    reorder_fields()
    delete_status_kp()
    verify_order()
