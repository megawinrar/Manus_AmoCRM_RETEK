"""
FastAPI routes.
"""

import logging
from fastapi import APIRouter, Request, BackgroundTasks, Depends
from src.infrastructure.amocrm_client import AmoClient
from src.application.webhook_service import WebhookService
from src.application.action3_service import Action3Service
from src.infrastructure.yadisk_client import YaDiskClient
from src.api.dependencies import get_amo_client, get_yadisk_client

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "RETEK amoCRM Microservice v2 (Clean Arch)"
    }

@router.post("/webhook")
async def amocrm_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    amo_client: AmoClient = Depends(get_amo_client),
    yadisk_client: YaDiskClient = Depends(get_yadisk_client)
):
    """
    Единый webhook для всех событий из amoCRM.
    """
    form_data = await request.form()
    
    # 1. Создание сделки
    if "leads[add][0][id]" in form_data:
        lead_id = int(form_data["leads[add][0][id]"])
        logger.info(f"Webhook: leads[add] ID={lead_id}")
        
        service = WebhookService(amo_client)
        background_tasks.add_task(service.handle_lead_add, lead_id)
        return {"status": "accepted", "event": "leads[add]"}
        
    # 2. Добавление примечания (Действие 3)
    note_id_keys = [k for k in form_data.keys() if k.startswith("notes[add]") and k.endswith("[id]")]
    if note_id_keys:
        idx = note_id_keys[0].split("][")[1]
        lead_id = int(form_data.get(f"notes[add][{idx}][element_id]", 0))
        note_text = form_data.get(f"notes[add][{idx}][text]", "")
        
        if lead_id and note_text:
            # Защита от бесконечного цикла
            if "🤖" in note_text or "✅" in note_text or "❌" in note_text:
                return {"status": "ignored", "reason": "bot_own_note"}
                
            trigger_words = ["распознай", "парсинг", "parse", "extract", "тендер"]
            has_trigger = any(word in note_text.lower() for word in trigger_words)
            has_link = "disk.yandex.ru" in note_text or "yadi.sk" in note_text or "disk:/" in note_text
            
            if has_trigger or has_link:
                logger.info(f"Webhook: notes[add] Action3 triggered for lead {lead_id}")
                service = Action3Service(amo_client, yadisk_client)
                background_tasks.add_task(service.process_note, lead_id, note_text)
                return {"status": "accepted", "event": "notes[add]", "action": "action3"}
                
    return {"status": "ignored", "reason": "unhandled_event"}
