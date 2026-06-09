"""
Модуль бэкапа сделок amoCRM.

Функции:
1. Полный дамп всех сделок (все воронки) через API → JSON
2. Сохранение на Яндекс.Диск (/ТОРГИ/_BACKUP/) и/или локально
3. Инкрементальный бэкап (только изменённые с последнего дампа)
4. Хранение истории: до/после обогащения

Расписание: ежедневно в 03:00 (ночной cron)

Лимиты API amoCRM:
- GET /leads: до 250 за запрос, пагинация через page
- Rate limit: 7 запросов/сек
- При 400 сделках = 2 запроса → ~1 сек
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

# Добавляем корень проекта
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════

AMO_DOMAIN = os.getenv("AMO_DOMAIN")
AMO_TOKEN = os.getenv("AMO_ACCESS_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {AMO_TOKEN}",
    "Content-Type": "application/json",
}
BASE_URL = f"https://{AMO_DOMAIN}/api/v4"

# Пути для бэкапов
BACKUP_DIR = os.path.join(PROJECT_ROOT, "data", "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

# Яндекс.Диск
YADISK_TOKEN = os.getenv("YADISK_TOKEN")
YADISK_BACKUP_FOLDER = "/ТОРГИ/_BACKUP"

# Все воронки
PIPELINES = {
    "active": int(os.getenv("AMO_PIPELINE_ACTIVE_ID")),
    "archive_directions": int(os.getenv("AMO_PIPELINE_ARCHIVE_DIRECTIONS_ID")),
    "archive_soz": int(os.getenv("AMO_PIPELINE_ARCHIVE_SOZ_ID")),
}


# ═══════════════════════════════════════════════════════════════
# ПОЛУЧЕНИЕ СДЕЛОК ИЗ amoCRM
# ═══════════════════════════════════════════════════════════════

def fetch_all_leads(with_notes: bool = True, with_contacts: bool = True) -> list:
    """
    Получить все сделки из всех воронок.
    
    Args:
        with_notes: Включить заметки (увеличивает время)
        with_contacts: Включить контакты
    
    Returns:
        Список всех сделок с полями и заметками
    """
    all_leads = []
    
    # Формируем параметр with
    with_params = []
    if with_contacts:
        with_params.append("contacts")
    # Заметки получаем отдельно (нет параметра with для notes в /leads)
    
    params = {
        "limit": 250,
        "page": 1,
    }
    if with_params:
        params["with"] = ",".join(with_params)
    
    while True:
        resp = requests.get(f"{BASE_URL}/leads", params=params, headers=HEADERS)
        
        if resp.status_code == 204:
            # Нет данных
            break
        
        if resp.status_code != 200:
            logger.error(f"Ошибка API: {resp.status_code} {resp.text}")
            break
        
        data = resp.json()
        leads = data.get("_embedded", {}).get("leads", [])
        
        if not leads:
            break
        
        all_leads.extend(leads)
        logger.info(f"  Получено {len(leads)} сделок (страница {params['page']}, всего {len(all_leads)})")
        
        # Проверяем пагинацию
        next_link = data.get("_links", {}).get("next")
        if not next_link:
            break
        
        params["page"] += 1
        time.sleep(0.2)  # Rate limit safety
    
    # Получаем заметки для каждой сделки (если нужно)
    if with_notes and all_leads:
        logger.info(f"  Получаю заметки для {len(all_leads)} сделок...")
        for lead in all_leads:
            lead["_notes"] = fetch_lead_notes(lead["id"])
            time.sleep(0.15)  # Rate limit
    
    return all_leads


def fetch_lead_notes(lead_id: int) -> list:
    """Получить все заметки сделки."""
    notes = []
    params = {"limit": 250, "page": 1}
    
    while True:
        resp = requests.get(
            f"{BASE_URL}/leads/{lead_id}/notes",
            params=params,
            headers=HEADERS,
        )
        
        if resp.status_code == 204:
            break
        if resp.status_code != 200:
            break
        
        data = resp.json()
        items = data.get("_embedded", {}).get("notes", [])
        if not items:
            break
        
        notes.extend(items)
        
        next_link = data.get("_links", {}).get("next")
        if not next_link:
            break
        params["page"] += 1
    
    return notes


def fetch_tasks() -> list:
    """Получить все задачи."""
    all_tasks = []
    params = {"limit": 250, "page": 1}
    
    while True:
        resp = requests.get(f"{BASE_URL}/tasks", params=params, headers=HEADERS)
        
        if resp.status_code == 204:
            break
        if resp.status_code != 200:
            break
        
        data = resp.json()
        tasks = data.get("_embedded", {}).get("tasks", [])
        if not tasks:
            break
        
        all_tasks.extend(tasks)
        
        next_link = data.get("_links", {}).get("next")
        if not next_link:
            break
        params["page"] += 1
        time.sleep(0.2)
    
    return all_tasks


# ═══════════════════════════════════════════════════════════════
# СОХРАНЕНИЕ БЭКАПА
# ═══════════════════════════════════════════════════════════════

def save_backup_local(leads: list, tasks: list = None) -> str:
    """
    Сохранить бэкап локально в JSON.
    
    Returns:
        Путь к файлу бэкапа
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"backup_{timestamp}.json"
    filepath = os.path.join(BACKUP_DIR, filename)
    
    backup_data = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "domain": AMO_DOMAIN,
            "leads_count": len(leads),
            "tasks_count": len(tasks) if tasks else 0,
            "pipelines": PIPELINES,
        },
        "leads": leads,
        "tasks": tasks or [],
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)
    
    file_size = os.path.getsize(filepath)
    logger.info(f"  Бэкап сохранён: {filepath} ({file_size / 1024:.1f} KB)")
    
    # Ротация: оставляем последние 30 файлов
    _rotate_backups(BACKUP_DIR, keep=30)
    
    return filepath


def save_backup_yadisk(local_path: str) -> bool:
    """
    Загрузить бэкап на Яндекс.Диск.
    
    Args:
        local_path: Путь к локальному файлу бэкапа
    
    Returns:
        True если успешно
    """
    if not YADISK_TOKEN:
        logger.warning("YADISK_TOKEN не задан — пропускаю загрузку на Яндекс.Диск")
        return False
    
    filename = os.path.basename(local_path)
    yadisk_path = f"{YADISK_BACKUP_FOLDER}/{filename}"
    
    # Создаём папку если нет
    requests.put(
        "https://cloud-api.yandex.net/v1/disk/resources",
        params={"path": YADISK_BACKUP_FOLDER},
        headers={"Authorization": f"OAuth {YADISK_TOKEN}"},
    )
    
    # Получаем URL для загрузки
    resp = requests.get(
        "https://cloud-api.yandex.net/v1/disk/resources/upload",
        params={"path": yadisk_path, "overwrite": "true"},
        headers={"Authorization": f"OAuth {YADISK_TOKEN}"},
    )
    
    if resp.status_code != 200:
        logger.error(f"Ошибка получения URL загрузки: {resp.status_code} {resp.text}")
        return False
    
    upload_url = resp.json().get("href")
    if not upload_url:
        return False
    
    # Загружаем файл
    with open(local_path, "rb") as f:
        resp = requests.put(upload_url, data=f)
    
    if resp.status_code in (200, 201, 202):
        logger.info(f"  Бэкап загружен на Яндекс.Диск: {yadisk_path}")
        return True
    else:
        logger.error(f"Ошибка загрузки на Яндекс.Диск: {resp.status_code}")
        return False


def _rotate_backups(directory: str, keep: int = 30):
    """Оставить только последние N файлов бэкапа."""
    files = sorted(Path(directory).glob("backup_*.json"), key=os.path.getmtime)
    if len(files) > keep:
        for f in files[:-keep]:
            f.unlink()
            logger.info(f"  Ротация: удалён старый бэкап {f.name}")


# ═══════════════════════════════════════════════════════════════
# ИНКРЕМЕНТАЛЬНЫЙ БЭКАП (до/после обогащения)
# ═══════════════════════════════════════════════════════════════

def save_lead_snapshot(lead_id: int, event: str = "before_enrichment") -> str:
    """
    Сохранить снимок одной сделки (для истории обогащения).
    
    Args:
        lead_id: ID сделки
        event: Тип события (before_enrichment, after_enrichment, before_archive)
    
    Returns:
        Путь к файлу снимка
    """
    snapshots_dir = os.path.join(BACKUP_DIR, "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)
    
    # Получаем текущее состояние сделки
    resp = requests.get(f"{BASE_URL}/leads/{lead_id}", headers=HEADERS)
    if resp.status_code != 200:
        logger.error(f"Не удалось получить сделку {lead_id}: {resp.status_code}")
        return ""
    
    lead_data = resp.json()
    
    # Получаем заметки
    notes = fetch_lead_notes(lead_id)
    lead_data["_notes"] = notes
    
    # Сохраняем
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"lead_{lead_id}_{event}_{timestamp}.json"
    filepath = os.path.join(snapshots_dir, filename)
    
    snapshot = {
        "meta": {
            "lead_id": lead_id,
            "event": event,
            "timestamp": datetime.now().isoformat(),
        },
        "lead": lead_data,
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    
    logger.info(f"  Снимок сохранён: {filepath}")
    return filepath


# ═══════════════════════════════════════════════════════════════
# ОСНОВНАЯ ФУНКЦИЯ (для cron)
# ═══════════════════════════════════════════════════════════════

def run_backup(with_notes: bool = True, upload_yadisk: bool = True):
    """
    Выполнить полный бэкап.
    Вызывается из APScheduler (cron) или вручную.
    """
    logger.info("=" * 50)
    logger.info("[BACKUP] Начинаю полный бэкап amoCRM...")
    logger.info("=" * 50)
    
    start = time.time()
    
    # 1. Получаем все сделки
    logger.info("[BACKUP] Получаю сделки...")
    leads = fetch_all_leads(with_notes=with_notes)
    logger.info(f"[BACKUP] Получено {len(leads)} сделок")
    
    # 2. Получаем задачи
    logger.info("[BACKUP] Получаю задачи...")
    tasks = fetch_tasks()
    logger.info(f"[BACKUP] Получено {len(tasks)} задач")
    
    # 3. Сохраняем локально
    logger.info("[BACKUP] Сохраняю локально...")
    local_path = save_backup_local(leads, tasks)
    
    # 4. Загружаем на Яндекс.Диск
    if upload_yadisk:
        logger.info("[BACKUP] Загружаю на Яндекс.Диск...")
        save_backup_yadisk(local_path)
    
    elapsed = time.time() - start
    logger.info(f"[BACKUP] Готово за {elapsed:.1f} сек. Сделок: {len(leads)}, задач: {len(tasks)}")
    
    return {
        "leads_count": len(leads),
        "tasks_count": len(tasks),
        "local_path": local_path,
        "elapsed_sec": elapsed,
    }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    
    parser = argparse.ArgumentParser(description="Бэкап сделок amoCRM")
    parser.add_argument("--no-notes", action="store_true", help="Не получать заметки (быстрее)")
    parser.add_argument("--no-yadisk", action="store_true", help="Не загружать на Яндекс.Диск")
    parser.add_argument("--snapshot", type=int, help="Сохранить снимок одной сделки (ID)")
    parser.add_argument("--snapshot-event", default="manual", help="Тип события для снимка")
    args = parser.parse_args()
    
    if args.snapshot:
        path = save_lead_snapshot(args.snapshot, args.snapshot_event)
        if path:
            print(f"Снимок сохранён: {path}")
    else:
        result = run_backup(
            with_notes=not args.no_notes,
            upload_yadisk=not args.no_yadisk,
        )
        print(f"\nИтог: {result['leads_count']} сделок, {result['tasks_count']} задач")
        print(f"Файл: {result['local_path']}")
        print(f"Время: {result['elapsed_sec']:.1f} сек")
