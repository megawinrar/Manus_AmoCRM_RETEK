"""
Обработчик вебхуков amoCRM — FastAPI endpoints.

Обрабатывает:
- leads[status] — смена статуса сделки → создание задачи по правилам
- leads[add] — создание сделки (информационное логирование)

amoCRM отправляет POST с Content-Type: application/x-www-form-urlencoded
Формат данных: leads[status][0][id], leads[status][0][status_id], etc.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException

from .amo_client import AmoClient
from .config import (
    PIPELINE_ACTIVE,
    ActiveStatuses,
    Fields,
    Users,
    get_status_task_rules,
    get_status_note_map,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_amo_client() -> AmoClient:
    """Получить экземпляр AmoClient (не dry-run в продакшене)."""
    return AmoClient(dry_run=False)


# ═══════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINT
# ═══════════════════════════════════════════════════════════════════

@router.post("/webhook")
async def handle_webhook(request: Request):
    """
    Основной endpoint для вебхуков amoCRM.
    
    amoCRM отправляет данные в формате form-urlencoded:
    leads[status][0][id] = 12345
    leads[status][0][status_id] = 67890
    leads[status][0][pipeline_id] = 10984442
    leads[status][0][old_status_id] = 11111
    leads[status][0][old_pipeline_id] = 10984442
    leads[status][0][responsible_user_id] = 99999
    """
    try:
        # amoCRM sends form data, not JSON
        form_data = await request.form()
        body = dict(form_data)

        logger.info(f"Webhook received: {len(body)} fields")

        # Определяем тип события
        if any(k.startswith("leads[status]") for k in body.keys()):
            return await _handle_status_change(body)
        elif any(k.startswith("leads[add]") for k in body.keys()):
            return await _handle_lead_add(body)
        else:
            logger.debug(f"Unhandled webhook type. Keys: {list(body.keys())[:10]}")
            return {"status": "ignored", "reason": "unhandled_event_type"}

    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        # Всегда возвращаем 200 чтобы amoCRM не ретраил
        return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════════════
# ОБРАБОТКА СМЕНЫ СТАТУСА
# ═══════════════════════════════════════════════════════════════════

async def _handle_status_change(body: dict) -> dict:
    """
    Обработка события leads[status] — смена статуса сделки.
    
    Логика:
    1. Извлечь lead_id, new_status_id, pipeline_id
    2. Проверить что это наша активная воронка
    3. Найти правило в STATUS_TASK_RULES
    4. Создать задачу через API
    """
    # Парсим данные из form-encoded формата
    lead_data = _parse_lead_status_data(body)
    if not lead_data:
        return {"status": "ignored", "reason": "cannot_parse_lead_data"}

    lead_id = lead_data["id"]
    new_status_id = lead_data["status_id"]
    pipeline_id = lead_data["pipeline_id"]
    old_status_id = lead_data.get("old_status_id")
    responsible_user_id = lead_data.get("responsible_user_id")

    logger.info(
        f"Status change: lead={lead_id}, "
        f"status {old_status_id} → {new_status_id}, "
        f"pipeline={pipeline_id}"
    )

    # Проверяем что это наша активная воронка
    if pipeline_id != PIPELINE_ACTIVE:
        logger.debug(f"Ignoring: pipeline {pipeline_id} != active {PIPELINE_ACTIVE}")
        return {"status": "ignored", "reason": "not_active_pipeline"}

    client = get_amo_client()

    # Записываем заметку в ленту карточки для любого статуса
    note_map = get_status_note_map()
    note_text = note_map.get(new_status_id)
    if note_text:
        client.add_note(lead_id=lead_id, text=note_text)
        logger.info(f"Note added to lead {lead_id} for status {new_status_id}")

    # Ищем правило для нового статуса
    rules = get_status_task_rules()
    rule = rules.get(new_status_id)

    if not rule:
        logger.debug(f"No task rule for status_id={new_status_id}")
        return {"status": "ok", "action": "note_added_no_task_rule", "lead_id": lead_id}

    # Определяем ответственного за задачу
    task_responsible = rule.get("responsible_user_id")
    if task_responsible is None:
        # _LEAD_RESPONSIBLE — берём из самой сделки
        task_responsible = responsible_user_id or Users.EMPLOYEE_2_SALES

    if not task_responsible:
        logger.warning(f"No responsible user for lead {lead_id}, using EMPLOYEE_2")
        task_responsible = Users.EMPLOYEE_2_SALES

    # Создаём задачу
    task = client.create_task(
        lead_id=lead_id,
        text=rule["text"],
        responsible_user_id=task_responsible,
        deadline_seconds=rule["deadline_seconds"],
        task_type_id=rule.get("task_type_id", 1),
    )

    if task:
        logger.info(
            f"Task created for lead {lead_id}: "
            f"'{rule['text'][:50]}...' → user {task_responsible}"
        )
        return {
            "status": "ok",
            "action": "task_created",
            "lead_id": lead_id,
            "task_id": task.get("id"),
            "note_added": bool(note_text),
        }
    else:
        logger.error(f"Failed to create task for lead {lead_id}")
        return {"status": "error", "action": "task_creation_failed", "lead_id": lead_id}


# ═══════════════════════════════════════════════════════════════════
# ОБРАБОТКА СОЗДАНИЯ СДЕЛКИ
# ═══════════════════════════════════════════════════════════════════

async def _handle_lead_add(body: dict) -> dict:
    """Логирование создания новой сделки (информационно)."""
    lead_id = body.get("leads[add][0][id]", "?")
    lead_name = body.get("leads[add][0][name]", "?")
    logger.info(f"New lead created: id={lead_id}, name='{lead_name}'")
    return {"status": "ok", "action": "lead_add_logged", "lead_id": lead_id}


# ═══════════════════════════════════════════════════════════════════
# ПАРСИНГ ДАННЫХ ВЕБХУКА
# ═══════════════════════════════════════════════════════════════════

def _parse_lead_status_data(body: dict) -> Optional[dict]:
    """
    Парсит form-encoded данные вебхука amoCRM.
    
    Ожидаемые ключи:
    leads[status][0][id]
    leads[status][0][status_id]
    leads[status][0][pipeline_id]
    leads[status][0][old_status_id]
    leads[status][0][old_pipeline_id]
    leads[status][0][responsible_user_id]
    """
    try:
        result = {}
        prefix = "leads[status][0]"

        # Обязательные поля
        lead_id = body.get(f"{prefix}[id]")
        status_id = body.get(f"{prefix}[status_id]")
        pipeline_id = body.get(f"{prefix}[pipeline_id]")

        if not all([lead_id, status_id, pipeline_id]):
            logger.warning(f"Missing required fields in webhook data")
            return None

        result["id"] = int(lead_id)
        result["status_id"] = int(status_id)
        result["pipeline_id"] = int(pipeline_id)

        # Опциональные поля
        old_status = body.get(f"{prefix}[old_status_id]")
        if old_status:
            result["old_status_id"] = int(old_status)

        old_pipeline = body.get(f"{prefix}[old_pipeline_id]")
        if old_pipeline:
            result["old_pipeline_id"] = int(old_pipeline)

        responsible = body.get(f"{prefix}[responsible_user_id]")
        if responsible:
            result["responsible_user_id"] = int(responsible)

        return result

    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing webhook data: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "RETEK amoCRM Microservice",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/webhook/test")
async def webhook_test():
    """Тестовый endpoint для проверки доступности."""
    return {"status": "ok", "message": "Webhook endpoint is reachable"}
