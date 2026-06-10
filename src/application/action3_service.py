"""
Action 3 (note_lead) use cases.
"""

import os
import re
import shutil
import tempfile
import logging
from src.infrastructure.amocrm_client import AmoClient
from src.infrastructure.yadisk_client import YaDiskClient
from src.domain.enums import Fields
from src.domain.rules import resolve_routing, build_lead_name
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
try:
    from scripts.extract_and_classify import extract_file, parse_tender_fields, validate_and_ocr_fallback
except ImportError:
    extract_file = None
    parse_tender_fields = None
    validate_and_ocr_fallback = None

logger = logging.getLogger(__name__)

class Action3Service:
    def __init__(self, amo_client: AmoClient, yadisk_client: YaDiskClient):
        self.amo = amo_client
        self.yadisk = yadisk_client

    def extract_link(self, text: str) -> str:
        """Извлекает ссылку на Я.Диск из текста."""
        patterns = [
            r'(https?://disk\.yandex\.ru/d/[a-zA-Z0-9_-]+)',
            r'(https?://yadi\.sk/d/[a-zA-Z0-9_-]+)',
            r'(disk:/[^\s\n]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return ""

    def process_note(self, lead_id: int, text: str) -> dict:
        """Обработка примечания (Действие 3)."""
        link = self.extract_link(text)
        if not link:
            return {"status": "ignored", "reason": "no_link"}
            
        logger.info(f"Action3: Found link {link} in lead {lead_id}")
        self.amo.add_note(lead_id, "🤖 Принял ссылку на Яндекс.Диск. Начинаю скачивание и анализ файлов...")
        
        # Скачиваем файлы
        temp_dir = tempfile.mkdtemp(prefix=f"action3_{lead_id}_")
        try:
            downloaded = self._download_files(link, temp_dir)
            if not downloaded:
                self.amo.add_note(lead_id, "❌ Ошибка: не удалось скачать файлы по ссылке.")
                return {"status": "error", "reason": "download_failed"}
                
            # Запускаем классификатор
            result = self._classify_files(temp_dir, downloaded)
            
            # Обновляем сделку
            self._update_lead(lead_id, result)
            
            return {"status": "ok", "action": "processed"}
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _classify_files(self, temp_dir: str, files: list) -> dict:
        """Запускает extract_and_classify на скачанных файлах."""
        if not extract_file or not parse_tender_fields:
            logger.error("extract_and_classify not available")
            return {"priority": "Р4 — Наблюдаем", "direction": "Не наш ассортимент"}

        full_text = ""
        file_names = []
        for f in os.listdir(temp_dir):
            filepath = os.path.join(temp_dir, f)
            if os.path.isfile(filepath):
                file_names.append(f)
                text, _ = extract_file(filepath)
                if text:
                    full_text += text + "\n"

        parsed = parse_tender_fields(full_text, file_names)

        if validate_and_ocr_fallback:
            pdf_files = [os.path.join(temp_dir, f) for f in file_names if f.lower().endswith('.pdf')]
            parsed = validate_and_ocr_fallback(parsed, pdf_files, full_text)

        return parsed

    def _download_files(self, link: str, target_dir: str) -> bool:
        """Скачивает файлы по публичной или внутренней ссылке."""
        if link.startswith("disk:/"):
            path = link.replace("disk:/", "/")
            items = self.yadisk.get_folder_items(path)
            for item in items:
                if item["type"] == "file":
                    url = self.yadisk.get_download_url(item["path"])
                    if url:
                        self.yadisk.download_file(url, os.path.join(target_dir, item["name"]))
            return bool(items)
        else:
            items = self.yadisk.get_public_folder_items(link)
            for item in items:
                if item["type"] == "file":
                    url = self.yadisk.get_public_download_url(link, item["path"])
                    if url:
                        self.yadisk.download_file(url, os.path.join(target_dir, item["name"]))
            return bool(items)

    def _update_lead(self, lead_id: int, result: dict):
        """Обновляет поля сделки на основе результата классификации."""
        custom_fields = []
        
        if result.get("customer"):
            custom_fields.append({"field_id": Fields.CUSTOMER, "values": [{"value": result["customer"]}]})
        
        priority = result.get("priority", "Р4")
        direction = result.get("direction", "Не наш ассортимент")
        situation = result.get("situation_type", "Стандарт")
        
        custom_fields.append({"field_id": Fields.PRIORITY, "values": [{"value": priority}]})
        custom_fields.append({"field_id": Fields.DIRECTION, "values": [{"value": direction}]})
        custom_fields.append({"field_id": Fields.SITUATION_TYPE, "values": [{"value": situation}]})
        
        if result.get("nmc"):
            custom_fields.append({"field_id": Fields.NMC, "values": [{"value": result["nmc"]}]})
            
        if result.get("deadline"):
            custom_fields.append({"field_id": Fields.DEADLINE, "values": [{"value": result["deadline"]}]})

        status_id, responsible_id = resolve_routing(priority, situation)
        name = build_lead_name(priority, result.get("customer", "Неизвестно"))

        self.amo.update_lead(
            lead_id=lead_id,
            status_id=status_id,
            responsible_user_id=responsible_id,
            custom_fields=custom_fields
        )
        
        report = (
            f"✅ Распознавание завершено!\n\n"
            f"Заказчик: {result.get('customer')}\n"
            f"НМЦ: {result.get('nmc')} руб.\n"
            f"Направление: {direction}\n"
            f"Приоритет: {priority}\n"
            f"Дедлайн: {result.get('deadline')}\n\n"
            f"Сделка маршрутизирована."
        )
        self.amo.add_note(lead_id, report)
