"""
Webhook use cases.
"""

import logging
from src.infrastructure.amocrm_client import AmoClient
from src.domain.enums import ActiveStatuses, Fields
from src.domain.rules import resolve_routing
from src.domain.notes import get_status_note_map

logger = logging.getLogger(__name__)

class WebhookService:
    def __init__(self, amo_client: AmoClient):
        self.amo = amo_client
        self.status_notes = get_status_note_map()

    def handle_lead_add(self, lead_id: int) -> dict:
        """Обработка создания новой сделки."""
        logger.info(f"Processing add_lead: {lead_id}")
        
        # Получаем сделку
        lead = self.amo.get_lead(lead_id)
        if not lead:
            return {"status": "error", "reason": "lead_not_found"}
            
        # Проверяем статус - реагируем только на LLM_RECOGNIZED
        status_id = lead.get("status_id")
        if status_id != ActiveStatuses.LLM_RECOGNIZED:
            return {"status": "ignored", "reason": "wrong_status"}
            
        # Извлекаем поля
        custom_fields = lead.get("custom_fields_values") or []
        fields_map = {cf["field_id"]: cf["values"][0]["value"] for cf in custom_fields}
        
        priority = fields_map.get(Fields.PRIORITY, "")
        situation_type = fields_map.get(Fields.SITUATION_TYPE, "")
        
        if not priority or not situation_type:
            return {"status": "ignored", "reason": "missing_routing_fields"}
            
        # Маршрутизация
        new_status, new_user = resolve_routing(priority, situation_type)
        
        # Обновляем сделку
        success = self.amo.update_lead(
            lead_id=lead_id,
            status_id=new_status,
            responsible_user_id=new_user
        )
        
        if success:
            note_text = self.status_notes.get(new_status, "")
            if note_text:
                self.amo.add_note(lead_id, note_text)
                
        return {"status": "ok", "action": "routed"}
