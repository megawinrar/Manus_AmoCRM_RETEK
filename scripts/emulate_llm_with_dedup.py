"""
Эмуляция LLM-классификатора с полной дедупликацией и обогащением.

Порядок работы:
1. Хешируем файлы тендера
2. Проверяем SQLite (точный путь → хеши файлов → fuzzy-match)
3. Проверяем API amoCRM (GET /leads?query=... → поиск по заказчику/номеру)
4. Если ТОЧНЫЙ дубль → СТОП (ничего не делаем)
5. Если ОБОГАЩЕНИЕ → обновляем существующую карточку (поля + заметка)
6. Если FUZZY дубль → создаём, но предупреждаем
7. Если НОВЫЙ → создаём сделку + задачу + заметку
8. Записываем/обновляем в SQLite
9. Сохраняем снимок (бэкап) при обогащении

Использование:
    python scripts/emulate_llm_with_dedup.py \\
        --files /path/to/file1.pdf /path/to/file2.docx \\
        --tender-path "/ТОРГИ/09.06.2026/Gesac - 86 поз." \\
        --customer "АО «НПО «Высокоточные комплексы»" \\
        --nmc 6719075.91 \\
        --priority P2 \\
        --direction CARBIDE-STANDARD \\
        --situation "Запрос котировок / реальные торги" \\
        --procedure-type "Запрос котировок" \\
        --procedure-number "SP26061000158" \\
        --positions 86 \\
        --deadline "2026-06-10" \\
        --comment "Описание тендера" \\
        --confidence 0.97
"""

import argparse
import hashlib
import os
import sys
import time
import requests
from datetime import datetime, timedelta

# Добавляем корень проекта в path
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from src.microservice.deduplication import (
    DeduplicationDB, TenderDeduplicator, FileRecord, compute_file_hash
)
from src.microservice.cron_backup import save_lead_snapshot

# ═══════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════

AMO_DOMAIN = os.getenv("AMO_DOMAIN")
AMO_TOKEN = os.getenv("AMO_ACCESS_TOKEN")
PIPELINE_ID = int(os.getenv("AMO_PIPELINE_ACTIVE_ID"))

HEADERS = {
    "Authorization": f"Bearer {AMO_TOKEN}",
    "Content-Type": "application/json",
}
BASE_URL = f"https://{AMO_DOMAIN}/api/v4"

# Статусы
STATUS_5_PURCHASING = int(os.getenv("STATUS_5_PURCHASING"))
STATUS_3_SOZ_CALL = int(os.getenv("STATUS_3_SOZ_CALL"))
STATUS_11_ARCHIVE = int(os.getenv("STATUS_11_ARCHIVE"))
STATUS_2_CHECK = int(os.getenv("STATUS_2_CHECK"))

# Пользователи
USER_EMPLOYEE_2 = int(os.getenv("USER_EMPLOYEE_2"))
USER_EMPLOYEE_3 = int(os.getenv("USER_EMPLOYEE_3"))

# Поля
FIELD_CUSTOMER = int(os.getenv("FIELD_CUSTOMER"))
FIELD_SITUATION_TYPE = int(os.getenv("FIELD_SITUATION_TYPE"))
FIELD_PRIORITY = int(os.getenv("FIELD_PRIORITY"))
FIELD_DIRECTION = int(os.getenv("FIELD_DIRECTION"))
FIELD_DIRECTION_SUBTYPE = int(os.getenv("FIELD_DIRECTION_SUBTYPE", "380313"))
FIELD_NMC = int(os.getenv("FIELD_NMC"))
FIELD_DEADLINE = int(os.getenv("FIELD_DEADLINE"))
FIELD_SOURCE = int(os.getenv("FIELD_SOURCE"))
FIELD_PROCEDURE_TYPE = int(os.getenv("FIELD_PROCEDURE_TYPE"))
FIELD_PROCEDURE_NUM = int(os.getenv("FIELD_PROCEDURE_NUM"))
FIELD_LLM_CONFIDENCE = int(os.getenv("FIELD_LLM_CONFIDENCE"))
FIELD_LLM_COMMENT = int(os.getenv("FIELD_LLM_COMMENT"))
FIELD_NEXT_ACTION = int(os.getenv("FIELD_NEXT_ACTION"))
FIELD_NEEDS_PURCHASE = int(os.getenv("FIELD_NEEDS_PURCHASE"))

# Enum IDs
ENUM_SITUATION = {
    "СОЗ": 215655,
    "Запрос котировок / реальные торги": 215657,
    "Неясно": 215659,
    "Не наш ассортимент": 215661,
}
ENUM_PRIORITY = {
    "P1": 215673, "Р1": 215673,
    "P2": 215675, "Р2": 215675,
    "P3": 215677, "Р3": 215677,
    "P4": 215679, "Р4": 215679,
}
ENUM_DIRECTION = {
    "SPEC-DRAWING": 215681,
    "HSS-STANDARD": 215683,
    "CARBIDE-STANDARD": 215685,
    "DIAMOND-STANDARD": 215687,
    "SOZ-DEVELOPMENT": 215689,
    "REAL-TENDER": 215691,
    "OUT-OF-SCOPE": 215693,
    "ARCHIVE-LEAD": 215695,
}
ENUM_PROCEDURE_TYPE = {
    "Запрос котировок": 215663,
    "Аукцион": 215665,
    "Конкурс": 215667,
    "Закупка у единственного поставщика": 215669,
    "Другое": 215671,
}
ENUM_SOURCE = {
    "Тендерная площадка": 215645,
    "Прямой запрос": 215647,
    "Email": 215649,
    "Телефон": 215651,
    "Другое": 215653,
}


# ═══════════════════════════════════════════════════════════════
# МАРШРУТИЗАЦИЯ
# ═══════════════════════════════════════════════════════════════

def resolve_routing(priority: str, situation: str) -> dict:
    """Определить статус и ответственного по правилам маршрутизации."""
    p = priority.upper().replace("Р", "P")  # Нормализуем

    if p == "P4" or situation == "Не наш ассортимент":
        return {
            "status_id": STATUS_11_ARCHIVE,
            "responsible_user_id": USER_EMPLOYEE_2,
            "status_name": "11. К архивированию",
        }

    if situation == "СОЗ":
        return {
            "status_id": STATUS_3_SOZ_CALL,
            "responsible_user_id": USER_EMPLOYEE_2,
            "status_name": "3. СОЗ — звонок / уточнить дату",
        }

    if situation == "Запрос котировок / реальные торги":
        return {
            "status_id": STATUS_5_PURCHASING,
            "responsible_user_id": USER_EMPLOYEE_3,
            "status_name": "5. Передано в закупку / расчёт",
        }

    # Неясно
    return {
        "status_id": STATUS_2_CHECK,
        "responsible_user_id": USER_EMPLOYEE_2,
        "status_name": "2. Проверка Сотрудника 2",
    }


# ═══════════════════════════════════════════════════════════════
# ПРОВЕРКА ДУБЛЕЙ ЧЕРЕЗ API amoCRM
# ═══════════════════════════════════════════════════════════════

def check_amo_duplicates(customer: str, nmc: float, procedure_number: str = None) -> list:
    """
    Проверить дубли через API amoCRM.
    Ищем по query (полнотекстовый поиск по названию сделки).
    """
    duplicates = []

    # Поиск по номеру процедуры (если есть)
    if procedure_number:
        resp = requests.get(
            f"{BASE_URL}/leads",
            params={"query": procedure_number, "limit": 10},
            headers=HEADERS,
        )
        if resp.status_code == 200:
            data = resp.json()
            leads = data.get("_embedded", {}).get("leads", [])
            for lead in leads:
                duplicates.append({
                    "id": lead["id"],
                    "name": lead["name"],
                    "status_id": lead["status_id"],
                    "pipeline_id": lead.get("pipeline_id"),
                    "match_type": "procedure_number",
                })

    # Поиск по заказчику (берём ключевое слово)
    if customer:
        search_term = customer.replace("АО", "").replace("ООО", "").replace("ПАО", "")
        search_term = search_term.replace("«", "").replace("»", "").replace('"', "").strip()
        words = [w for w in search_term.split() if len(w) > 3]
        if words:
            query = " ".join(words[:2])
            resp = requests.get(
                f"{BASE_URL}/leads",
                params={"query": query, "limit": 20},
                headers=HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                leads = data.get("_embedded", {}).get("leads", [])
                existing_ids = {d["id"] for d in duplicates}
                for lead in leads:
                    if lead["id"] not in existing_ids:
                        duplicates.append({
                            "id": lead["id"],
                            "name": lead["name"],
                            "status_id": lead["status_id"],
                            "pipeline_id": lead.get("pipeline_id"),
                            "price": lead.get("price", 0),
                            "match_type": "customer_name",
                        })

    return duplicates


# ═══════════════════════════════════════════════════════════════
# ОБОГАЩЕНИЕ СУЩЕСТВУЮЩЕЙ СДЕЛКИ
# ═══════════════════════════════════════════════════════════════

def enrich_existing_lead(
    lead_id: int,
    args,
    file_records: list,
    dedup_result,
    routing: dict,
) -> bool:
    """
    Обогатить существующую сделку новой информацией.
    
    Логика:
    - Сохраняем снимок "до"
    - Обновляем поля (если новая информация точнее)
    - Добавляем заметку об обогащении
    - Обновляем/создаём задачу если нужно
    - Сохраняем снимок "после"
    
    Returns:
        True если обогащение выполнено
    """
    print(f"\n  Обогащаю существующую сделку ID={lead_id}...")

    # 1. Сохраняем снимок "до"
    print(f"  [SNAPSHOT] Сохраняю состояние 'до'...")
    save_lead_snapshot(lead_id, "before_enrichment")
    time.sleep(0.5)

    # 2. Обновляем поля сделки
    print(f"  [PATCH] Обновляю поля...")
    fields_payload = []

    # Обновляем только если есть новая информация
    if args.customer:
        fields_payload.append({"field_id": FIELD_CUSTOMER, "values": [{"value": args.customer}]})
    if args.nmc > 0:
        fields_payload.append({"field_id": FIELD_NMC, "values": [{"value": args.nmc}]})
    if args.situation:
        fields_payload.append({"field_id": FIELD_SITUATION_TYPE, "values": [{"enum_id": ENUM_SITUATION.get(args.situation, 215659)}]})
    if args.priority:
        fields_payload.append({"field_id": FIELD_PRIORITY, "values": [{"enum_id": ENUM_PRIORITY.get(args.priority, 215679)}]})
    if args.direction:
        fields_payload.append({"field_id": FIELD_DIRECTION, "values": [{"enum_id": ENUM_DIRECTION.get(args.direction, 215695)}]})
    if args.procedure_number:
        fields_payload.append({"field_id": FIELD_PROCEDURE_NUM, "values": [{"value": args.procedure_number}]})
    if args.confidence:
        fields_payload.append({"field_id": FIELD_LLM_CONFIDENCE, "values": [{"value": args.confidence}]})

    # Обновляем LLM-комментарий
    enrichment_comment = (
        f"[ОБОГАЩЕНИЕ {datetime.now().strftime('%d.%m.%Y %H:%M')}]\n"
        f"Новые данные: {args.comment or 'повторная классификация'}\n"
        f"Новые файлы: {', '.join(dedup_result.new_files) if dedup_result.new_files else 'нет'}\n"
        f"Обновлённые файлы: {', '.join(dedup_result.updated_files) if dedup_result.updated_files else 'нет'}"
    )
    fields_payload.append({"field_id": FIELD_LLM_COMMENT, "values": [{"value": enrichment_comment}]})

    # Формируем обновлённое название
    priority_short = args.priority.replace("Р", "P").replace("P", "Р")
    customer_short = args.customer.replace("АО", "").replace("ООО", "").replace("«", "").replace("»", "").strip()
    if len(customer_short) > 30:
        customer_short = customer_short[:30]
    nmc_mln = args.nmc / 1_000_000
    deal_name = f"{priority_short} / {customer_short} / {args.positions} поз. / {nmc_mln:.1f} млн"

    # Дедлайн
    deadline_ts = None
    if args.deadline:
        try:
            deadline_dt = datetime.strptime(args.deadline, "%Y-%m-%d")
            deadline_ts = int(deadline_dt.timestamp())
            fields_payload.append({"field_id": FIELD_DEADLINE, "values": [{"value": deadline_ts}]})
        except ValueError:
            pass

    # PATCH запрос
    patch_payload = [
        {
            "id": lead_id,
            "name": deal_name,
            "pipeline_id": PIPELINE_ID,
            "status_id": routing["status_id"],
            "responsible_user_id": routing["responsible_user_id"],
            "price": int(args.nmc),
            "custom_fields_values": fields_payload,
        }
    ]

    resp = requests.patch(f"{BASE_URL}/leads", json=patch_payload, headers=HEADERS)
    if resp.status_code in (200, 201):
        print(f"  [PATCH] Сделка обновлена ✓")
        print(f"    Новое название: {deal_name}")
        print(f"    Статус: {routing['status_name']}")
    else:
        print(f"  [PATCH] ОШИБКА: {resp.status_code} {resp.text}")
        return False

    time.sleep(0.5)

    # 3. Добавляем заметку об обогащении
    print(f"  [NOTE] Добавляю заметку об обогащении...")
    file_list = "\n".join([f"- {fr.filename}" for fr in file_records])
    note_text = (
        f"📎 ОБОГАЩЕНИЕ КАРТОЧКИ\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Приоритет: {args.priority}\n"
        f"Направление: {args.direction}\n"
        f"Тип ситуации: {args.situation}\n"
        f"Заказчик: {args.customer}\n"
        f"НМЦ: {args.nmc:,.2f} руб.\n"
        f"Номер процедуры: {args.procedure_number}\n"
        f"Уверенность: {args.confidence}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    if dedup_result.new_files:
        note_text += f"Новые файлы:\n" + "\n".join([f"+ {f}" for f in dedup_result.new_files]) + "\n\n"
    if dedup_result.updated_files:
        note_text += f"Обновлённые файлы:\n" + "\n".join([f"↻ {f}" for f in dedup_result.updated_files]) + "\n\n"
    if dedup_result.unchanged_files:
        note_text += f"Без изменений: {len(dedup_result.unchanged_files)} файлов\n\n"

    note_text += (
        f"Маршрутизация: {args.priority} + {args.situation} → {routing['status_name']}\n\n"
        f"Все файлы тендера:\n{file_list}\n\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

    payload = [{"note_type": "common", "params": {"text": note_text}, "entity_id": lead_id}]
    resp = requests.post(f"{BASE_URL}/leads/{lead_id}/notes", json=payload, headers=HEADERS)
    if resp.status_code in (200, 201):
        print(f"  [NOTE] Заметка добавлена ✓")
    else:
        print(f"  [NOTE] ОШИБКА: {resp.status_code} {resp.text}")

    time.sleep(0.5)

    # 4. Обновляем задачу (создаём новую если есть новая информация)
    if dedup_result.new_files or dedup_result.updated_files:
        print(f"  [TASK] Создаю задачу на пересмотр...")
        task_text = (
            f"ОБОГАЩЕНИЕ: пересмотреть расчёт.\n\n"
            f"Карточка обогащена новыми данными:\n"
            f"- Новые файлы: {len(dedup_result.new_files)}\n"
            f"- Обновлённые файлы: {len(dedup_result.updated_files)}\n\n"
            f"Заказчик: {args.customer}\n"
            f"НМЦ: {args.nmc:,.2f} руб.\n"
            f"Позиций: {args.positions}\n"
            f"Срок подачи: {args.deadline}"
        )
        deadline = int((datetime.now() + timedelta(days=1)).timestamp())
        task_payload = [
            {
                "text": task_text,
                "complete_till": deadline,
                "responsible_user_id": routing["responsible_user_id"],
                "entity_id": lead_id,
                "entity_type": "leads",
                "task_type_id": 1,
            }
        ]
        resp = requests.post(f"{BASE_URL}/tasks", json=task_payload, headers=HEADERS)
        if resp.status_code in (200, 201):
            task_id = resp.json()["_embedded"]["tasks"][0]["id"]
            print(f"  [TASK] Задача создана: ID={task_id} ✓")
        else:
            print(f"  [TASK] ОШИБКА: {resp.status_code} {resp.text}")

    # 5. Сохраняем снимок "после"
    time.sleep(0.5)
    print(f"  [SNAPSHOT] Сохраняю состояние 'после'...")
    save_lead_snapshot(lead_id, "after_enrichment")

    return True


# ═══════════════════════════════════════════════════════════════
# СОЗДАНИЕ НОВОЙ СДЕЛКИ
# ═══════════════════════════════════════════════════════════════

def create_lead(deal_name: str, routing: dict, fields_payload: list, price: int) -> int:
    """Создать сделку в amoCRM. Возвращает lead_id или None."""
    payload = [
        {
            "name": deal_name,
            "pipeline_id": PIPELINE_ID,
            "status_id": routing["status_id"],
            "responsible_user_id": routing["responsible_user_id"],
            "price": price,
            "custom_fields_values": fields_payload,
        }
    ]

    resp = requests.post(f"{BASE_URL}/leads", json=payload, headers=HEADERS)
    if resp.status_code in (200, 201):
        data = resp.json()
        lead_id = data["_embedded"]["leads"][0]["id"]
        print(f"  [CREATE LEAD] Сделка создана: ID={lead_id}")
        print(f"    Название: {deal_name}")
        print(f"    Статус: {routing['status_name']}")
        return lead_id
    else:
        print(f"  [CREATE LEAD] ОШИБКА: {resp.status_code} {resp.text}")
        return None


def create_task(lead_id: int, text: str, responsible_user_id: int, days: int = 2) -> int:
    """Создать задачу для сделки."""
    deadline = int((datetime.now() + timedelta(days=days)).timestamp())
    payload = [
        {
            "text": text,
            "complete_till": deadline,
            "responsible_user_id": responsible_user_id,
            "entity_id": lead_id,
            "entity_type": "leads",
            "task_type_id": 1,
        }
    ]
    resp = requests.post(f"{BASE_URL}/tasks", json=payload, headers=HEADERS)
    if resp.status_code in (200, 201):
        task_id = resp.json()["_embedded"]["tasks"][0]["id"]
        print(f"  [CREATE TASK] Задача создана: ID={task_id}")
        return task_id
    else:
        print(f"  [CREATE TASK] ОШИБКА: {resp.status_code} {resp.text}")
        return None


def add_note(lead_id: int, note_text: str):
    """Добавить заметку в ленту сделки."""
    payload = [
        {
            "note_type": "common",
            "params": {"text": note_text},
            "entity_id": lead_id,
        }
    ]
    resp = requests.post(f"{BASE_URL}/leads/{lead_id}/notes", json=payload, headers=HEADERS)
    if resp.status_code in (200, 201):
        print(f"  [ADD NOTE] Заметка добавлена")
    else:
        print(f"  [ADD NOTE] ОШИБКА: {resp.status_code} {resp.text}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Эмуляция LLM-классификатора с дедупликацией")
    parser.add_argument("--files", nargs="+", required=True, help="Пути к файлам тендера")
    parser.add_argument("--tender-path", required=True, help="Путь на Яндекс.Диске (или виртуальный)")
    parser.add_argument("--customer", required=True, help="Название заказчика")
    parser.add_argument("--nmc", type=float, required=True, help="НМЦ в рублях")
    parser.add_argument("--priority", required=True, help="Приоритет: P1/P2/P3/P4")
    parser.add_argument("--direction", required=True, help="Направление: CARBIDE-STANDARD и т.д.")
    parser.add_argument("--situation", required=True, help="Тип ситуации")
    parser.add_argument("--procedure-type", default="Запрос котировок", help="Тип процедуры")
    parser.add_argument("--procedure-number", default="", help="Номер процедуры")
    parser.add_argument("--positions", type=int, default=0, help="Количество позиций")
    parser.add_argument("--deadline", default="", help="Дедлайн подачи (YYYY-MM-DD)")
    parser.add_argument("--comment", default="", help="LLM комментарий")
    parser.add_argument("--confidence", type=float, default=0.9, help="Уверенность LLM (0-1)")
    parser.add_argument("--source", default="Тендерная площадка", help="Источник")
    parser.add_argument("--force", action="store_true", help="Игнорировать дубли и создать новую")
    args = parser.parse_args()

    print("=" * 60)
    print("LLM-КЛАССИФИКАТОР (эмуляция с дедупликацией + обогащением)")
    print("=" * 60)
    print(f"\n  Заказчик: {args.customer}")
    print(f"  НМЦ: {args.nmc:,.2f} руб.")
    print(f"  Приоритет: {args.priority}")
    print(f"  Направление: {args.direction}")
    print(f"  Тип ситуации: {args.situation}")
    print(f"  Уверенность: {args.confidence}")
    print(f"  Файлов: {len(args.files)}")
    print()

    # ─── Шаг 1: Хешируем файлы ───
    print("─" * 60)
    print("[ШАГ 1] Хеширование файлов...")
    file_records = []
    for fpath in args.files:
        if not os.path.exists(fpath):
            print(f"  ПРЕДУПРЕЖДЕНИЕ: файл не найден: {fpath}")
            continue
        fhash = compute_file_hash(fpath)
        fsize = os.path.getsize(fpath)
        fname = os.path.basename(fpath)
        file_records.append(FileRecord(
            filename=fname, file_hash=fhash, file_size=fsize, file_path=fpath
        ))
        print(f"  {fname} → {fhash[:12]}... ({fsize:,} bytes)")
    print(f"  Итого: {len(file_records)} файлов захешировано")
    print()

    # ─── Шаг 2: Проверка SQLite ───
    print("─" * 60)
    print("[ШАГ 2] Проверка SQLite (локальная дедупликация)...")
    db = DeduplicationDB(os.path.join(PROJECT_ROOT, "data", "processed_tenders.db"))
    dedup = TenderDeduplicator(db)
    dedup_result = dedup.check(
        tender_path=args.tender_path,
        files=file_records,
        customer=args.customer,
        nmc=args.nmc,
    )

    # Маршрутизация (нужна для обогащения и создания)
    routing = resolve_routing(args.priority, args.situation)

    if dedup_result.is_exact_duplicate:
        print(f"  ✓ ТОЧНЫЙ ДУБЛЬ (SQLite): все файлы идентичны")
        print(f"  Существующая сделка: ID={dedup_result.existing_lead_id}")
        print(f"\n  СТОП. Ничего не делаем — файлы не изменились.")
        print(f"  Карточка: https://{AMO_DOMAIN}/leads/detail/{dedup_result.existing_lead_id}")
        return

    elif dedup_result.is_enrichment or dedup_result.is_update:
        # ОБОГАЩЕНИЕ: есть новые или обновлённые файлы
        action = "ОБОГАЩЕНИЕ" if dedup_result.is_enrichment else "ОБНОВЛЕНИЕ"
        print(f"  → {action}: {dedup_result.message}")
        if dedup_result.new_files:
            print(f"    Новые файлы: {dedup_result.new_files}")
        if dedup_result.updated_files:
            print(f"    Обновлённые файлы: {dedup_result.updated_files}")
        print(f"  Существующая сделка: ID={dedup_result.existing_lead_id}")
        print()

        # Обогащаем существующую карточку
        print("─" * 60)
        print(f"[ШАГ 3] Обогащение сделки ID={dedup_result.existing_lead_id}...")
        success = enrich_existing_lead(
            lead_id=dedup_result.existing_lead_id,
            args=args,
            file_records=file_records,
            dedup_result=dedup_result,
            routing=routing,
        )

        # Обновляем SQLite
        if success:
            print()
            print("─" * 60)
            print("[ШАГ 4] Обновление SQLite...")
            db.save_tender(
                tender_path=args.tender_path,
                files=file_records,
                lead_id=dedup_result.existing_lead_id,
                customer=args.customer,
                nmc=args.nmc,
                position_count=args.positions,
                direction=args.direction,
                date_folder=datetime.now().strftime("%d.%m.%Y"),
            )
            print(f"  SQLite обновлён ✓")

        print()
        print("=" * 60)
        print(f"ГОТОВО! Карточка обогащена.")
        print(f"  Сделка: https://{AMO_DOMAIN}/leads/detail/{dedup_result.existing_lead_id}")
        print(f"  Действие: {action}")
        print("=" * 60)
        return

    elif dedup_result.is_fuzzy_duplicate:
        print(f"  ⚠️ ВОЗМОЖНЫЙ ДУБЛЬ (fuzzy): {dedup_result.message}")
        print(f"  Существующая сделка: ID={dedup_result.existing_lead_id}")
        print(f"  Совпадение: {dedup_result.match_score:.0%}")
        print(f"  → Создаю НОВУЮ карточку (fuzzy — не точный дубль)")
        print()

    elif dedup_result.is_new:
        print(f"  ✓ Новый тендер — дублей в SQLite не найдено")
        print()

    # ─── Шаг 3: Проверка API amoCRM ───
    print("─" * 60)
    print("[ШАГ 3] Проверка API amoCRM (онлайн дедупликация)...")
    amo_dupes = check_amo_duplicates(args.customer, args.nmc, args.procedure_number)

    if amo_dupes:
        print(f"  Найдено {len(amo_dupes)} похожих сделок в amoCRM:")
        for d in amo_dupes:
            price_str = f", НМЦ={d.get('price', 0):,}" if d.get('price') else ""
            print(f"    • ID={d['id']}: \"{d['name']}\" (match: {d['match_type']}{price_str})")

        if not args.force:
            # Проверяем: если все найденные дубли в архиве (дубли) — это нормально
            archive_pipeline = int(os.getenv("AMO_PIPELINE_ARCHIVE_DIRECTIONS_ID"))
            active_dupes = [d for d in amo_dupes if d.get("pipeline_id") != archive_pipeline]

            if active_dupes:
                print(f"\n  СТОП. Активные похожие сделки существуют.")
                print(f"  Используйте --force для принудительного создания.")
                return
            else:
                print(f"  (все найденные — в архиве, продолжаем)")
    else:
        print(f"  Дублей в amoCRM не найдено ✓")
    print()

    # ─── Шаг 4: Создание новой сделки ───
    print("─" * 60)
    print("[ШАГ 4] Маршрутизация + создание сделки...")
    print(f"  Статус: {routing['status_name']}")
    print(f"  Ответственный: User ID={routing['responsible_user_id']}")
    print()

    # Формируем название
    priority_short = args.priority.replace("Р", "P").replace("P", "Р")
    customer_short = args.customer.replace("АО", "").replace("ООО", "").replace("«", "").replace("»", "").strip()
    if len(customer_short) > 30:
        customer_short = customer_short[:30]
    nmc_mln = args.nmc / 1_000_000
    deal_name = f"{priority_short} / {customer_short} / {args.positions} поз. / {nmc_mln:.1f} млн"

    # Дедлайн
    deadline_ts = None
    if args.deadline:
        try:
            deadline_dt = datetime.strptime(args.deadline, "%Y-%m-%d")
            deadline_ts = int(deadline_dt.timestamp())
        except ValueError:
            pass

    # Формируем custom_fields_values
    fields_payload = [
        {"field_id": FIELD_CUSTOMER, "values": [{"value": args.customer}]},
        {"field_id": FIELD_SITUATION_TYPE, "values": [{"enum_id": ENUM_SITUATION.get(args.situation, 215659)}]},
        {"field_id": FIELD_PRIORITY, "values": [{"enum_id": ENUM_PRIORITY.get(args.priority, 215679)}]},
        {"field_id": FIELD_DIRECTION, "values": [{"enum_id": ENUM_DIRECTION.get(args.direction, 215695)}]},
        {"field_id": FIELD_NMC, "values": [{"value": args.nmc}]},
        {"field_id": FIELD_SOURCE, "values": [{"enum_id": ENUM_SOURCE.get(args.source, 215653)}]},
        {"field_id": FIELD_PROCEDURE_TYPE, "values": [{"enum_id": ENUM_PROCEDURE_TYPE.get(args.procedure_type, 215671)}]},
        {"field_id": FIELD_LLM_CONFIDENCE, "values": [{"value": args.confidence}]},
        {"field_id": FIELD_LLM_COMMENT, "values": [{"value": args.comment or "Эмуляция LLM-классификатора"}]},
        {"field_id": FIELD_NEXT_ACTION, "values": [{"value": "Рассчитать себестоимость, подготовить КП"}]},
        {"field_id": FIELD_NEEDS_PURCHASE, "values": [{"value": True}]},
    ]

    if deadline_ts:
        fields_payload.append({"field_id": FIELD_DEADLINE, "values": [{"value": deadline_ts}]})
    if args.procedure_number:
        fields_payload.append({"field_id": FIELD_PROCEDURE_NUM, "values": [{"value": args.procedure_number}]})

    price = int(args.nmc)
    lead_id = create_lead(deal_name, routing, fields_payload, price)

    if not lead_id:
        print("\n  Не удалось создать сделку. Прерываю.")
        sys.exit(1)

    time.sleep(1)

    # ─── Шаг 5: Задача ───
    task_text = (
        f"Рассчитать себестоимость, подготовить КП.\n\n"
        f"Заказчик: {args.customer}\n"
        f"НМЦ: {args.nmc:,.2f} руб.\n"
        f"Позиций: {args.positions}\n"
        f"Направление: {args.direction}\n"
        f"Номер процедуры: {args.procedure_number}\n"
        f"Срок подачи: {args.deadline}"
    )
    create_task(lead_id, task_text, routing["responsible_user_id"])

    time.sleep(1)

    # ─── Шаг 6: Заметка ───
    file_list = "\n".join([f"- {fr.filename}" for fr in file_records])
    note_text = (
        f"🆕 LLM-классификатор (эмуляция)\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Приоритет: {args.priority}\n"
        f"Направление: {args.direction}\n"
        f"Тип ситуации: {args.situation}\n"
        f"Заказчик: {args.customer}\n"
        f"НМЦ: {args.nmc:,.2f} руб.\n"
        f"Номер процедуры: {args.procedure_number}\n"
        f"Уверенность: {args.confidence}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Комментарий: {args.comment}\n\n"
        f"Маршрутизация: {args.priority} + {args.situation} → {routing['status_name']}\n\n"
        f"Файлы тендера:\n{file_list}\n\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    add_note(lead_id, note_text)

    # ─── Шаг 7: Записываем в SQLite ───
    print()
    print("─" * 60)
    print("[ШАГ 5] Запись в SQLite (дедупликация)...")
    db.save_tender(
        tender_path=args.tender_path,
        files=file_records,
        lead_id=lead_id,
        customer=args.customer,
        nmc=args.nmc,
        position_count=args.positions,
        direction=args.direction,
        date_folder=datetime.now().strftime("%d.%m.%Y"),
    )
    print(f"  Записано: tender_path={args.tender_path}, lead_id={lead_id}")
    print(f"  Файлов в базе: {len(file_records)}")
    print()

    # ─── Итог ───
    print("=" * 60)
    print("ГОТОВО! Новая сделка создана.")
    print(f"  Сделка: https://{AMO_DOMAIN}/leads/detail/{lead_id}")
    print(f"  Статус: {routing['status_name']}")
    print(f"  SQLite: записано")
    print("=" * 60)


if __name__ == "__main__":
    main()
