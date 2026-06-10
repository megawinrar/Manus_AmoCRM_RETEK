"""
Обработчик Действия 3: Распознавание тендера из примечания со ссылкой на Яндекс.Диск.
"""
import os
import re
import json
import logging
import tempfile
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from .amo_client import AmoClient
from .config import (
    ActiveStatuses,
    Users,
    resolve_routing,
    build_lead_name,
    get_status_note,
    STATUS_TASK_RULES,
)

logger = logging.getLogger(__name__)

# Регулярки для поиска ссылки на Я.Диск
# Поддерживает как публичные ссылки (yadi.sk/d/..., disk.yandex.ru/d/...), так и внутренние пути (disk:/ТОРГИ/...)
YADISK_PUBLIC_LINK_RE = re.compile(r'https?://(?:disk\.yandex\.[a-z]{2,3}|yadi\.sk)/d/[a-zA-Z0-9_-]+')
YADISK_PATH_RE = re.compile(r'(?:disk:)?(/ТОРГИ/[^\s\n\r]+)')

# Вспомогательные константы для полей из config
FIELD_CUSTOMER = int(os.getenv("FIELD_CUSTOMER", "380299"))
FIELD_NMC = int(os.getenv("FIELD_NMC", "380315"))
FIELD_DIRECTION = int(os.getenv("FIELD_DIRECTION", "380311"))
FIELD_PRIORITY = int(os.getenv("FIELD_PRIORITY", "380309"))
FIELD_PROCEDURE_NUM = int(os.getenv("FIELD_PROCEDURE_NUM", "380303"))
FIELD_SITUATION_TYPE = int(os.getenv("FIELD_SITUATION_TYPE", "380305"))
FIELD_DEADLINE = int(os.getenv("FIELD_DEADLINE", "380317"))
FIELD_LLM_CONFIDENCE = int(os.getenv("FIELD_LLM_CONFIDENCE", "380349"))
FIELD_LLM_COMMENT = int(os.getenv("FIELD_LLM_COMMENT", "380351"))

# Enum IDs (from emulate_llm_with_dedup)
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
ENUM_SITUATION = {
    "СОЗ": 215655,
    "Запрос котировок / реальные торги": 215657,
    "Неясно": 215659,
    "Не наш ассортимент": 215661,
}

SUPPORTED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".rtf", ".txt", ".png", ".jpg", ".jpeg"
}

def extract_yadisk_link(text: str) -> Optional[str]:
    """Извлекает ссылку на Я.Диск из текста."""
    # Сначала ищем публичную ссылку
    match = YADISK_PUBLIC_LINK_RE.search(text)
    if match:
        return match.group(0)
        
    # Затем внутренний путь
    match = YADISK_PATH_RE.search(text)
    if match:
        path = match.group(1)
        if not path.startswith("disk:"):
            path = "disk:" + path
        return path
        
    return None

def download_from_public_link(public_url: str, tmp_dir: str) -> List[str]:
    """Скачивает файлы по публичной ссылке на Я.Диск."""
    api_url = "https://cloud-api.yandex.net/v1/disk/public/resources"
    
    # 1. Получаем список файлов
    def get_files_recursive(path=""):
        params = {"public_key": public_url, "limit": 100}
        if path:
            params["path"] = path
            
        resp = requests.get(api_url, params=params)
        if resp.status_code != 200:
            logger.error(f"Failed to get public dir: {resp.status_code}")
            return []
            
        items = resp.json().get("_embedded", {}).get("items", [])
        files = []
        
        for item in items:
            name = item["name"]
            # Пропускаем скрытые файлы
            if name.startswith("._") or name.startswith("~$"):
                continue
                
            if item["type"] == "file":
                ext = os.path.splitext(name)[1].lower()
                if ext in SUPPORTED_EXTENSIONS or ext == ".zip":
                    files.append({
                        "name": name,
                        "path": item["path"],
                        "size": item.get("size", 0)
                    })
            elif item["type"] == "dir":
                files.extend(get_files_recursive(item["path"]))
                
        return files

    files_to_download = get_files_recursive()
    logger.info(f"Found {len(files_to_download)} files in public link")
    
    downloaded_files = []
    dl_url_api = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
    
    for f in files_to_download:
        # Получаем прямую ссылку
        dl_resp = requests.get(dl_url_api, params={"public_key": public_url, "path": f["path"]})
        if dl_resp.status_code != 200:
            continue
            
        href = dl_resp.json().get("href")
        if not href:
            continue
            
        # Скачиваем файл
        local_path = os.path.join(tmp_dir, f["name"])
        # Handle duplicates in flat folder
        counter = 1
        while os.path.exists(local_path):
            name_no_ext, ext = os.path.splitext(f["name"])
            local_path = os.path.join(tmp_dir, f"{name_no_ext}_{counter}{ext}")
            counter += 1
            
        try:
            r = requests.get(href, stream=True)
            with open(local_path, "wb") as out_f:
                for chunk in r.iter_content(chunk_size=8192):
                    out_f.write(chunk)
            downloaded_files.append(local_path)
            logger.info(f"Downloaded: {f['name']}")
        except Exception as e:
            logger.error(f"Error downloading {f['name']}: {e}")
            
    return downloaded_files

def download_from_internal_path(path: str, tmp_dir: str) -> List[str]:
    """Скачивает файлы по внутреннему пути Я.Диска, используя cron_yadisk."""
    try:
        from .cron_yadisk import YaDiskClient, collect_files_recursive
        client = YaDiskClient()
        
        path_without_disk = path.replace("disk:", "")
        files_info = collect_files_recursive(client, path_without_disk, depth=0)
        
        downloaded_files = []
        for file_info in files_info:
            local_name = os.path.basename(file_info["path"])
            local_path = os.path.join(tmp_dir, local_name)
            
            # Handle duplicates
            counter = 1
            while os.path.exists(local_path):
                name_no_ext, ext = os.path.splitext(local_name)
                local_path = os.path.join(tmp_dir, f"{name_no_ext}_{counter}{ext}")
                counter += 1
                
            if client.download_file(file_info["path"], local_path):
                downloaded_files.append(local_path)
                
        return downloaded_files
    except Exception as e:
        logger.error(f"Error downloading internal path: {e}")
        return []

def run_extraction_and_classification(files: List[str]) -> Dict[str, Any]:
    """Запускает extract_and_classify на скачанных файлах."""
    try:
        import sys
        project_root = Path(__file__).parent.parent.parent
        scripts_dir = project_root / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.append(str(scripts_dir))
            
        import extract_and_classify as ec_module
        
        # 1. Извлекаем текст
        all_text = ""
        for f in files:
            if os.path.exists(f):
                text = ec_module.extract_file(f)
                if isinstance(text, tuple):
                    text = text[0]
                all_text += text + "\n"
                
        # 2. Парсим поля
        parsed = ec_module.parse_tender_fields(all_text, files)
        
        # 3. Валидация + OCR fallback
        pdf_files = [f for f in files if f.lower().endswith('.pdf')]
        parsed = ec_module.validate_and_ocr_fallback(parsed, pdf_files, all_text)
        
        return parsed
    except Exception as e:
        logger.error(f"Extraction error: {e}", exc_info=True)
        return {"error": str(e)}

async def process_action3(lead_id: int, note_text: str) -> bool:
    """
    Основная функция Действия 3.
    1. Ищет ссылку
    2. Скачивает файлы
    3. Распознаёт
    4. Обновляет сделку
    """
    link = extract_yadisk_link(note_text)
    if not link:
        return False
        
    client = AmoClient()
    
    # 1. Уведомляем о начале
    client.add_note(lead_id, f"🤖 Найдена ссылка на Яндекс.Диск. Начинаю скачивание файлов и распознавание тендера...\n{link}")
    
    # 2. Скачиваем файлы
    tmp_dir = tempfile.mkdtemp(prefix=f"action3_{lead_id}_")
    
    try:
        if link.startswith("http"):
            downloaded_files = download_from_public_link(link, tmp_dir)
        else:
            downloaded_files = download_from_internal_path(link, tmp_dir)
            
        if not downloaded_files:
            client.add_note(lead_id, "❌ Ошибка: Не удалось скачать файлы по ссылке. Проверьте доступность папки.")
            return True
            
        # Распаковываем ZIP если есть
        try:
            from .cron_yadisk import extract_archives
            all_files = extract_archives(downloaded_files, tmp_dir)
        except ImportError:
            all_files = downloaded_files
            
        client.add_note(lead_id, f"✅ Скачано файлов: {len(all_files)}. Запускаю анализ...")
        
        # 3. Распознавание
        parsed = run_extraction_and_classification(all_files)
        
        if "error" in parsed:
            client.add_note(lead_id, f"❌ Ошибка распознавания: {parsed['error']}")
            return True
            
        # 4. Обновление карточки
        # Подготовка данных
        customer = parsed.get("customer") or ""
        nmc = parsed.get("nmc") or 0
        if isinstance(nmc, str):
            try:
                nmc = float(nmc.replace(" ", "").replace(",", "."))
            except (ValueError, AttributeError):
                nmc = 0
        direction = parsed.get("direction_hint") or parsed.get("direction") or "CARBIDE-STANDARD"
        priority = parsed.get("priority_hint") or parsed.get("priority") or "P3"
        deadline = parsed.get("deadline") or ""
        procedure_number = parsed.get("procedure_number") or ""
        situation = parsed.get("situation_type") or "Неясно"
        confidence = parsed.get("confidence_scores") or parsed.get("confidence") or {}
        
        # Определяем маршрутизацию
        status_id, responsible_user_id = resolve_routing(priority, situation)
        
        # Формируем поля
        fields_payload = []
        if customer:
            fields_payload.append({"field_id": FIELD_CUSTOMER, "values": [{"value": customer}]})
        if nmc and nmc > 0:
            fields_payload.append({"field_id": FIELD_NMC, "values": [{"value": int(nmc)}]})
        if situation and situation in ENUM_SITUATION:
            fields_payload.append({"field_id": FIELD_SITUATION_TYPE, "values": [{"enum_id": ENUM_SITUATION[situation]}]})
        if direction and direction in ENUM_DIRECTION:
            fields_payload.append({"field_id": FIELD_DIRECTION, "values": [{"enum_id": ENUM_DIRECTION[direction]}]})
        if procedure_number:
            fields_payload.append({"field_id": FIELD_PROCEDURE_NUM, "values": [{"value": procedure_number}]})
        if priority and priority in ENUM_PRIORITY:
            fields_payload.append({"field_id": FIELD_PRIORITY, "values": [{"enum_id": ENUM_PRIORITY[priority]}]})
            
        if confidence:
            fields_payload.append({"field_id": FIELD_LLM_CONFIDENCE, "values": [{"value": json.dumps(confidence, ensure_ascii=False)}]})
            
        enrichment_comment = (
            f"[ОБОГАЩЕНИЕ ЧЕРЕЗ ЧАТ {datetime.now().strftime('%d.%m.%Y %H:%M')}]\n"
            f"Валидация: {parsed.get('validation_status', 'unknown')}\n"
            f"Файлов обработано: {len(all_files)}"
        )
        fields_payload.append({"field_id": FIELD_LLM_COMMENT, "values": [{"value": enrichment_comment}]})
        
        if deadline:
            try:
                deadline_dt = datetime.strptime(deadline, "%Y-%m-%d")
                deadline_ts = int(deadline_dt.timestamp())
                fields_payload.append({"field_id": FIELD_DEADLINE, "values": [{"value": deadline_ts}]})
            except ValueError:
                pass
                
        # PATCH запрос
        patch_data = {
            "status_id": status_id,
            "responsible_user_id": responsible_user_id,
            "custom_fields_values": fields_payload,
        }
        
        if nmc and nmc > 0:
            patch_data["price"] = int(nmc)
            
        # Обновляем название
        priority_enum_id = ENUM_PRIORITY.get(priority, 215677)
        deadline_str = ""
        if deadline:
            try:
                dt = datetime.strptime(deadline, "%Y-%m-%d")
                deadline_str = dt.strftime("%d.%m")
            except ValueError:
                pass
                
        new_name = build_lead_name(
            priority_enum_id=priority_enum_id,
            customer=customer,
            deadline_str=deadline_str
        )
        if new_name:
            patch_data["name"] = new_name
            
        # Отправляем PATCH
        client.update_lead(lead_id, patch_data)
        
        # 5. Заметка с результатами
        file_list = "\n".join([f"- {os.path.basename(f)}" for f in all_files])
        result_note = (
            f"🎯 РАСПОЗНАВАНИЕ ЗАВЕРШЕНО\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Приоритет: {priority}\n"
            f"Направление: {direction}\n"
            f"Тип ситуации: {situation}\n"
            f"Заказчик: {customer}\n"
            f"НМЦ: {nmc:,.2f} руб.\n"
            f"Номер процедуры: {procedure_number}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Обработанные файлы:\n{file_list}\n"
        )
        client.add_note(lead_id, result_note)
        
        # Добавляем статусную заметку если есть
        status_note = get_status_note(str(status_id))
        if status_note:
            client.add_note(lead_id, status_note)
            
        # Создаем задачу по правилам
        rules = STATUS_TASK_RULES
        rule = None
        for key, val in rules.items():
            if val.get("status_id") == status_id: # Если бы в правилах был status_id
                pass
                
        # Просто создаем дефолтную задачу проверки
        task_responsible = responsible_user_id or Users.EMPLOYEE_2_SALES
        client.create_task(
            lead_id=lead_id,
            text="Проверить классификацию (распознано из чата)",
            responsible_user_id=task_responsible,
            deadline_seconds=2 * 3600,
            task_type_id=1
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Action 3 error: {e}", exc_info=True)
        client.add_note(lead_id, f"❌ Системная ошибка при обработке: {e}")
        return True
    finally:
        # Очистка tmp
        import shutil
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass
