"""
Deduplication use cases.
"""

import logging
from typing import Optional
from src.infrastructure.amocrm_client import AmoClient
from src.domain.models import TenderFile, DeduplicationResult
from src.domain.enums import Fields, Pipelines

logger = logging.getLogger(__name__)

class DeduplicationService:
    def __init__(self, amo_client: AmoClient):
        self.amo = amo_client

    def check_duplicate(self, tender_file: TenderFile) -> DeduplicationResult:
        """
        Уровень 1: Проверка по хэшу файла.
        """
        logger.info(f"Checking duplicate for {tender_file.filename} (hash: {tender_file.file_hash})")
        
        # Ищем сделку с таким же хэшем
        query = tender_file.file_hash
        leads = self.amo.get_leads(query=query)
        
        for lead in leads:
            custom_fields = lead.get("custom_fields_values") or []
            for cf in custom_fields:
                if cf["field_id"] == Fields.FILE_HASH:
                    for val in cf["values"]:
                        if val["value"] == tender_file.file_hash:
                            return DeduplicationResult(
                                is_new=False,
                                is_exact_duplicate=True,
                                existing_lead_id=lead["id"]
                            )
                            
        return DeduplicationResult(is_new=True)

    def process_new_file(self, tender_file: TenderFile) -> Optional[int]:
        """Обработка нового файла: дедупликация + создание/обновление."""
        result = self.check_duplicate(tender_file)
        
        if result.is_exact_duplicate:
            logger.info(f"Exact duplicate found: Lead {result.existing_lead_id}")
            self.amo.add_note(
                result.existing_lead_id, 
                f"⚠️ Попытка загрузить дубликат файла: {tender_file.filename}"
            )
            return result.existing_lead_id
            
        # Упрощенная версия для рефакторинга
        # В реальности здесь должна быть классификация через LLM
        return None
