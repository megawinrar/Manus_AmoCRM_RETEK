"""
Cron background jobs use cases.
"""

import logging
from src.infrastructure.amocrm_client import AmoClient
from src.domain.enums import ActiveStatuses, Fields, Pipelines
from src.domain.rules import auto_escalate_priority

logger = logging.getLogger(__name__)

class CronService:
    def __init__(self, amo_client: AmoClient):
        self.amo = amo_client

    def check_deadlines_and_escalate(self):
        """Ежечасная проверка дедлайнов и эскалация приоритетов."""
        logger.info("Starting check_deadlines_and_escalate")
        
        # Получаем все активные сделки
        leads = self.amo.get_leads(pipeline_id=Pipelines.ACTIVE)
        
        for lead in leads:
            self._process_lead_escalation(lead)
            
    def _process_lead_escalation(self, lead: dict):
        """Проверка и эскалация одной сделки."""
        lead_id = lead["id"]
        status_id = lead["status_id"]
        
        # Игнорируем архивированные
        if status_id == ActiveStatuses.TO_ARCHIVE:
            return
            
        # Извлекаем поля
        custom_fields = lead.get("custom_fields_values") or []
        fields_map = {cf["field_id"]: cf["values"][0]["value"] for cf in custom_fields}
        
        current_priority = fields_map.get(Fields.PRIORITY, "")
        deadline = fields_map.get(Fields.DEADLINE, "")
        
        if not current_priority or not deadline:
            return
            
        # Проверяем эскалацию
        new_priority, reason = auto_escalate_priority(current_priority, deadline)
        
        if new_priority != current_priority:
            logger.info(f"Escalating lead {lead_id} from {current_priority} to {new_priority}. Reason: {reason}")
            
            self.amo.update_lead(
                lead_id=lead_id,
                custom_fields=[{"field_id": Fields.PRIORITY, "values": [{"value": new_priority}]}]
            )
            
            self.amo.add_note(
                lead_id, 
                f"⚠️ Автоэскалация приоритета: {current_priority} ➡️ {new_priority}\nПричина: {reason}"
            )
