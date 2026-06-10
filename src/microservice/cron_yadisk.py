"""
Модуль опроса Яндекс.Диска — cron_yadisk.py

Запускается каждый час. Логика:
1. Обходит папку YADISK_ROOT_FOLDER (по умолчанию /ТОРГИ)
2. Ищет папки с датами (DD.MM.YYYY) — это дни загрузки
3. Внутри каждой даты — папки тендеров (название = описание тендера)
4. Внутри тендера — файлы (.xlsx, .docx, .doc, .pdf, .zip и т.д.)
5. Может быть ещё одна вложенность (подпапка с любым названием)
6. Дедупликация: хеширование файлов + fuzzy-match по заказчику/НМЦ
7. Сценарии: новый / дубль / обогащение / обновление / fuzzy-дубль
8. Новые тендеры → LLM-классификатор → сделка в amoCRM
9. Обогащение → обновление существующей карточки + заметка в ленту

Структура диска:
    /ТОРГИ/
    ├── 09.06.2026/
    │   ├── Gesac - 86 поз./
    │   │   ├── Gesac - 86 pos_RU.xlsx
    │   │   ├── ИоЗ.docx
    │   │   └── ...
    │   ├── АО ОКБ ФАКЕЛ - твердосплав 350к руб/
    │   │   └── подпапка/
    │   │       └── файлы...
    │   └── ...
    └── 10.06.2026/
        └── ...
"""

import os
import re
import json
import sqlite3
import hashlib
import logging
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════

YADISK_TOKEN = os.getenv("YADISK_TOKEN", "")
YADISK_ROOT_FOLDER = os.getenv("YADISK_ROOT_FOLDER", "/ТОРГИ")
YADISK_API_BASE = "https://cloud-api.yandex.net/v1/disk"

# SQLite для дедупликации (legacy — сохраняем для обратной совместимости)
DB_PATH = os.getenv("YADISK_DB_PATH", "data/processed_tenders.db")

# Поддерживаемые расширения файлов
SUPPORTED_EXTENSIONS = {
    ".xlsx", ".xls", ".docx", ".doc", ".pdf", ".zip", ".rar",
    ".7z", ".rtf", ".odt", ".ods", ".csv", ".txt", ".png",
    ".jpg", ".jpeg", ".tiff",
}

# Паттерн даты в названии папки (DD.MM.YYYY)
DATE_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

# Максимальная глубина рекурсии (дата → тендер → подпапка)
MAX_DEPTH = 3

# amoCRM
AMO_DOMAIN = os.getenv("AMO_DOMAIN", "")
AMO_TOKEN = os.getenv("AMO_ACCESS_TOKEN", "")
AMO_HEADERS = {
    "Authorization": f"Bearer {AMO_TOKEN}",
    "Content-Type": "application/json",
}
AMO_BASE_URL = f"https://{AMO_DOMAIN}/api/v4"

# amoCRM pipeline/status IDs
AMO_PIPELINE_ACTIVE = int(os.getenv("AMO_PIPELINE_ACTIVE_ID", "10984442"))
AMO_STATUS_LLM = int(os.getenv("STATUS_1_LLM", "0"))

# Custom field IDs
FIELD_CUSTOMER = int(os.getenv("FIELD_CUSTOMER", "380299"))
FIELD_NMC = int(os.getenv("FIELD_NMC", "380315"))
FIELD_DEADLINE = int(os.getenv("FIELD_DEADLINE", "380317"))
FIELD_DIRECTION = int(os.getenv("FIELD_DIRECTION", "380311"))
FIELD_PRIORITY = int(os.getenv("FIELD_PRIORITY", "380309"))
FIELD_SOURCE = int(os.getenv("FIELD_SOURCE", "380293"))
FIELD_DOCS_URL = int(os.getenv("FIELD_DOCS_URL", "380297"))
FIELD_LLM_CONFIDENCE = int(os.getenv("FIELD_LLM_CONFIDENCE", "380349"))
FIELD_LLM_COMMENT = int(os.getenv("FIELD_LLM_COMMENT", "380351"))
FIELD_PROCEDURE_NUM = int(os.getenv("FIELD_PROCEDURE_NUM", "380303"))
FIELD_SITUATION_TYPE = int(os.getenv("FIELD_SITUATION_TYPE", "380305"))

# User IDs
AMO_USER_RESPONSIBLE = int(os.getenv("USER_EMPLOYEE_2", "0"))


# ═══════════════════════════════════════════════════════════════════
# SQLITE: ДЕДУПЛИКАЦИЯ (LEGACY)
# ═══════════════════════════════════════════════════════════════════

def init_db() -> sqlite3.Connection:
    """Инициализировать SQLite базу для хранения обработанных тендеров."""
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_tenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_path TEXT UNIQUE NOT NULL,
            folder_name TEXT NOT NULL,
            date_folder TEXT NOT NULL,
            file_count INTEGER DEFAULT 0,
            total_size INTEGER DEFAULT 0,
            processed_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            amo_lead_id INTEGER,
            llm_result TEXT,
            error TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tender_id INTEGER NOT NULL,
            file_path TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            mime_type TEXT,
            downloaded_at TEXT,
            FOREIGN KEY (tender_id) REFERENCES processed_tenders(id)
        )
    """)
    conn.commit()
    return conn


def is_tender_processed(conn: sqlite3.Connection, folder_path: str) -> bool:
    """Проверить, был ли тендер уже обработан (legacy — для первичной проверки)."""
    cursor = conn.execute(
        "SELECT id, status FROM processed_tenders WHERE folder_path = ?",
        (folder_path,)
    )
    row = cursor.fetchone()
    if row is None:
        return False
    # Если статус 'pending' или 'error' — можно переобработать
    status = row[1]
    return status not in ("pending", "error")


def mark_tender_processed(
    conn: sqlite3.Connection,
    folder_path: str,
    folder_name: str,
    date_folder: str,
    file_count: int,
    total_size: int,
    status: str = "pending",
    amo_lead_id: Optional[int] = None,
    llm_result: Optional[str] = None,
    error: Optional[str] = None,
) -> int:
    """Записать тендер как обработанный. Возвращает ID записи."""
    cursor = conn.execute(
        """INSERT OR REPLACE INTO processed_tenders 
           (folder_path, folder_name, date_folder, file_count, total_size,
            processed_at, status, amo_lead_id, llm_result, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            folder_path, folder_name, date_folder, file_count, total_size,
            datetime.now().isoformat(), status, amo_lead_id, llm_result, error,
        )
    )
    conn.commit()
    return cursor.lastrowid


def update_tender_status(
    conn: sqlite3.Connection,
    folder_path: str,
    status: str,
    amo_lead_id: Optional[int] = None,
    llm_result: Optional[str] = None,
    error: Optional[str] = None,
):
    """Обновить статус обработки тендера."""
    conn.execute(
        """UPDATE processed_tenders 
           SET status = ?, amo_lead_id = ?, llm_result = ?, error = ?
           WHERE folder_path = ?""",
        (status, amo_lead_id, llm_result, error, folder_path)
    )
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
# ЯНДЕКС.ДИСК API
# ═══════════════════════════════════════════════════════════════════

class YaDiskClient:
    """Клиент для работы с Яндекс.Диск REST API."""

    def __init__(self, token: str = YADISK_TOKEN):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"OAuth {self.token}",
            "Accept": "application/json",
        })

    def list_folder(self, path: str, limit: int = 100) -> list[dict]:
        """
        Получить список элементов в папке.
        Возвращает список словарей с ключами: name, type, path, size, mime_type, modified.
        """
        items = []
        offset = 0

        while True:
            resp = self.session.get(
                f"{YADISK_API_BASE}/resources",
                params={"path": path, "limit": limit, "offset": offset},
            )

            if resp.status_code == 404:
                logger.warning(f"Папка не найдена: {path}")
                return []

            resp.raise_for_status()
            data = resp.json()

            embedded = data.get("_embedded", {})
            page_items = embedded.get("items", [])

            for item in page_items:
                items.append({
                    "name": item["name"],
                    "type": item["type"],
                    "path": item["path"].replace("disk:", ""),
                    "size": item.get("size", 0),
                    "mime_type": item.get("mime_type", ""),
                    "modified": item.get("modified", ""),
                })

            # Пагинация
            if len(page_items) < limit:
                break
            offset += limit

        return items

    def get_download_url(self, path: str) -> Optional[str]:
        """Получить прямую ссылку на скачивание файла."""
        resp = self.session.get(
            f"{YADISK_API_BASE}/resources/download",
            params={"path": path},
        )
        if resp.status_code != 200:
            logger.error(f"Не удалось получить ссылку на скачивание: {path} → {resp.status_code}")
            return None
        return resp.json().get("href")

    def download_file(self, path: str, local_path: str) -> bool:
        """Скачать файл с Яндекс.Диска в локальную папку."""
        url = self.get_download_url(path)
        if not url:
            return False

        resp = requests.get(url, stream=True)
        if resp.status_code != 200:
            logger.error(f"Ошибка скачивания: {path} → {resp.status_code}")
            return False

        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Скачан: {path} → {local_path}")
        return True


# ═══════════════════════════════════════════════════════════════════
# СКАНИРОВАНИЕ ПАПОК
# ═══════════════════════════════════════════════════════════════════

def scan_root_folder(client: YaDiskClient) -> list[dict]:
    """
    Сканировать корневую папку ТОРГИ.
    Возвращает ВСЕ тендеры (включая ранее обработанные — для дедупликации).
    """
    all_tenders = []

    # Уровень 1: папки с датами
    root_items = client.list_folder(YADISK_ROOT_FOLDER)
    date_folders = [
        item for item in root_items
        if item["type"] == "dir" and DATE_PATTERN.match(item["name"])
    ]

    logger.info(f"Найдено {len(date_folders)} папок с датами в {YADISK_ROOT_FOLDER}")

    for date_item in date_folders:
        date_name = date_item["name"]
        date_path = date_item["path"]

        # Уровень 2: папки тендеров
        tender_items = client.list_folder(date_path)
        tender_folders = [item for item in tender_items if item["type"] == "dir"]

        logger.info(f"  {date_name}: {len(tender_folders)} тендеров")

        for tender_item in tender_folders:
            tender_path = tender_item["path"]
            tender_name = tender_item["name"]

            # Уровень 3: файлы тендера (+ возможная подпапка)
            files = collect_files_recursive(client, tender_path, depth=0)

            if not files:
                logger.debug(f"    Пропуск (нет файлов): {tender_name}")
                continue

            all_tenders.append({
                "folder_path": tender_path,
                "folder_name": tender_name,
                "date_folder": date_name,
                "files": files,
            })

    logger.info(f"Всего тендеров на диске: {len(all_tenders)}")
    return all_tenders


def collect_files_recursive(client: YaDiskClient, path: str, depth: int = 0) -> list[dict]:
    """
    Рекурсивно собрать файлы из папки (до MAX_DEPTH уровней вложенности).
    Фильтрует по расширению и игнорирует скрытые файлы (._*).
    """
    if depth >= MAX_DEPTH:
        return []

    items = client.list_folder(path)
    files = []

    for item in items:
        if item["type"] == "file":
            name = item["name"]
            # Пропускаем скрытые файлы macOS (._*) и временные (~$*)
            if name.startswith("._") or name.startswith("~$"):
                continue
            # Проверяем расширение
            ext = os.path.splitext(name)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                files.append(item)
        elif item["type"] == "dir":
            # Рекурсия в подпапку
            sub_files = collect_files_recursive(client, item["path"], depth + 1)
            files.extend(sub_files)

    return files


# ═════════════════════════════════════════════════════════════════
# РАСПАКОВКА ZIP-АРХИВОВ
# ═════════════════════════════════════════════════════════════════

ARCHIVE_EXTENSIONS = {".zip"}


def extract_archives(file_paths: list[str], extract_dir: str) -> list[str]:
    """
    Проверяет список скачанных файлов — если среди них есть .zip,
    распаковывает их и возвращает обновлённый список файлов.
    """
    result_files = []

    for fpath in file_paths:
        ext = os.path.splitext(fpath)[1].lower()

        if ext in ARCHIVE_EXTENSIONS:
            extracted = _extract_zip(fpath, extract_dir)
            if extracted:
                result_files.extend(extracted)
                logger.info(
                    f"📦 Распакован {os.path.basename(fpath)}: "
                    f"{len(extracted)} файлов"
                )
            else:
                result_files.append(fpath)
                logger.warning(
                    f"⚠️ Не удалось распаковать: {os.path.basename(fpath)}"
                )
        else:
            result_files.append(fpath)

    return result_files


def _extract_zip(
    zip_path: str,
    extract_dir: str,
    max_files: int = 100,
    max_total_bytes: int = 500 * 1024 * 1024,
) -> list[str]:
    """Распаковать ZIP-архив во временную папку."""
    try:
        if not zipfile.is_zipfile(zip_path):
            logger.warning(f"Не является валидным ZIP: {zip_path}")
            return []

        extracted_files = []
        zip_basename = os.path.splitext(os.path.basename(zip_path))[0]
        out_dir = os.path.join(extract_dir, f"_unzipped_{zip_basename}")
        os.makedirs(out_dir, exist_ok=True)

        total_extracted_bytes = 0

        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.infolist()

            if len(members) > max_files:
                logger.warning(
                    f"ZIP содержит {len(members)} файлов "
                    f"(>макс {max_files}), ограничиваем"
                )
                members = members[:max_files]

            for member in members:
                if member.is_dir():
                    continue

                filename = member.filename

                # Защита от path traversal
                if ".." in filename or filename.startswith("/"):
                    continue

                # Пропускаем скрытые и системные
                basename = os.path.basename(filename)
                if (
                    basename.startswith("._")
                    or basename.startswith("~$")
                    or "__MACOSX" in filename
                ):
                    continue

                # Проверяем расширение
                ext = os.path.splitext(basename)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                # Проверяем лимит размера
                if total_extracted_bytes + member.file_size > max_total_bytes:
                    logger.warning(
                        f"Превышен лимит размера "
                        f"({max_total_bytes // 1024 // 1024} MB)"
                    )
                    break

                # Извлекаем файл (плоская структура)
                out_path = os.path.join(out_dir, basename)

                counter = 1
                while os.path.exists(out_path):
                    name_no_ext = os.path.splitext(basename)[0]
                    out_path = os.path.join(
                        out_dir, f"{name_no_ext}_{counter}{ext}"
                    )
                    counter += 1

                with zf.open(member) as src, open(out_path, "wb") as dst:
                    dst.write(src.read())

                total_extracted_bytes += member.file_size
                extracted_files.append(out_path)

        # Рекурсия: вложенные zip (один уровень)
        nested_zips = [f for f in extracted_files if f.endswith(".zip")]
        for nested_zip in nested_zips:
            extracted_files.remove(nested_zip)
            nested_extracted = _extract_zip(
                nested_zip, out_dir,
                max_files=50,
                max_total_bytes=max_total_bytes,
            )
            extracted_files.extend(nested_extracted)

        return extracted_files

    except zipfile.BadZipFile:
        logger.error(f"Повреждённый ZIP: {zip_path}")
        return []
    except Exception as e:
        logger.error(f"Ошибка распаковки {zip_path}: {e}")
        return []


# ═════════════════════════════════════════════════════════════════
# ИНТЕГРАЦИЯ С ДЕДУПЛИКАЦИЕЙ
# ═════════════════════════════════════════════════════════════════

def _post_note_to_lead(lead_id: int, text: str):
    """Написать заметку в ленту карточки amoCRM."""
    try:
        payload = [{"note_type": "common", "params": {"text": text}}]
        resp = requests.post(
            f"{AMO_BASE_URL}/leads/{lead_id}/notes",
            json=payload,
            headers=AMO_HEADERS,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            logger.info(f"Заметка записана в lead {lead_id}")
        else:
            logger.error(f"Ошибка записи заметки: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Ошибка при записи заметки: {e}")


def _update_lead_fields(lead_id: int, custom_fields: list[dict]):
    """Обновить поля карточки amoCRM."""
    try:
        payload = {"custom_fields_values": custom_fields}
        resp = requests.patch(
            f"{AMO_BASE_URL}/leads/{lead_id}",
            json=payload,
            headers=AMO_HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"Поля обновлены для lead {lead_id}")
        else:
            logger.error(f"Ошибка обновления полей: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении полей: {e}")


def _create_amo_lead(result: dict, folder_name: str, folder_path: str, date_folder: str) -> Optional[int]:
    """
    Создать сделку в amoCRM на основе результатов классификации.
    Возвращает lead_id или None при ошибке.
    """
    if not AMO_TOKEN or not AMO_DOMAIN:
        logger.warning("AMO_TOKEN/AMO_DOMAIN не заданы — пропускаем создание сделки")
        return None

    customer = result.get("customer") or folder_name
    lead_name = f"[YaDisk] {customer}"
    if len(lead_name) > 200:
        lead_name = lead_name[:200]

    # Маппинг direction_hint → enum value в amoCRM
    DIRECTION_ENUM_MAP = {
        "SPEC-DRAWING": "SPEC-DRAWING \u2014 \u0441\u043f\u0435\u0446\u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442 \u043f\u043e \u0447\u0435\u0440\u0442\u0435\u0436\u0430\u043c / \u0422\u0417",
        "HSS-STANDARD": "HSS-STANDARD \u2014 \u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442\u043d\u044b\u0439 \u0431\u044b\u0441\u0442\u0440\u043e\u0440\u0435\u0437 / \u0413\u041e\u0421\u0422",
        "CARBIDE-STANDARD": "CARBIDE-STANDARD \u2014 \u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442\u043d\u044b\u0439 \u0442\u0432\u0435\u0440\u0434\u043e\u0441\u043f\u043b\u0430\u0432",
        "DIAMOND-STANDARD": "DIAMOND-STANDARD \u2014 \u0430\u043b\u043c\u0430\u0437\u043d\u044b\u0439 \u0438\u043d\u0441\u0442\u0440\u0443\u043c\u0435\u043d\u0442 \u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442\u043d\u044b\u0439",
        "SOZ-DEVELOPMENT": "SOZ-DEVELOPMENT \u2014 \u0421\u041e\u0417 / \u0440\u0430\u0437\u0432\u0438\u0442\u0438\u0435 / \u0431\u0443\u0434\u0443\u0449\u0438\u0439 \u0442\u043e\u0440\u0433",
        "REAL-TENDER": "REAL-TENDER \u2014 \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u0435 \u0442\u043e\u0440\u0433\u0438 / \u0437\u0430\u043f\u0440\u043e\u0441 \u043a\u043e\u0442\u0438\u0440\u043e\u0432\u043e\u043a",
        "OUT-OF-SCOPE": "OUT-OF-SCOPE \u2014 \u043d\u0435 \u043d\u0430\u0448 \u0430\u0441\u0441\u043e\u0440\u0442\u0438\u043c\u0435\u043d\u0442",
        "ARCHIVE-LEAD": "ARCHIVE-LEAD \u2014 \u0431\u0430\u0437\u0430 / \u043d\u0430\u0431\u043b\u044e\u0434\u0435\u043d\u0438\u0435 / \u0431\u0443\u0434\u0443\u0449\u0430\u044f \u043f\u0440\u043e\u0440\u0430\u0431\u043e\u0442\u043a\u0430",
    }
    # Маппинг priority → enum value в amoCRM
    PRIORITY_ENUM_MAP = {
        "P1": "\u04201 \u2014 \u0421\u0440\u043e\u0447\u043d\u043e",
        "P2": "\u04202 \u2014 \u0411\u044b\u0441\u0442\u0440\u044b\u0435 \u0414\u0435\u043d\u044c\u0433\u0438",
        "P3": "\u04203 \u2014 \u0421\u0440\u0435\u0434\u043d\u0438\u0435 \u0414\u0435\u043d\u044c\u0433\u0438",
        "P4": "\u04204 \u2014 \u041d\u0430\u0431\u043b\u044e\u0434\u0430\u0435\u043c / \u0412 \u0431\u0430\u0437\u0443",
    }

    # Формируем custom_fields_values
    custom_fields = []
    # Заказчик (text)
    if result.get("customer"):
        custom_fields.append({"field_id": FIELD_CUSTOMER, "values": [{"value": str(result["customer"])[:255]}]})
    # НМЦ (numeric) — передаём как int
    if result.get("nmc") and result["nmc"] > 0:
        custom_fields.append({"field_id": FIELD_NMC, "values": [{"value": int(result["nmc"])}]})
    # Срок подачи (date) — нужен unix timestamp или строка YYYY-MM-DD
    if result.get("deadline"):
        deadline_val = result["deadline"]
        # Преобразуем DD.MM.YYYY в unix timestamp
        try:
            from datetime import datetime as _dt
            if re.match(r'\d{2}\.\d{2}\.\d{4}', str(deadline_val)):
                dt = _dt.strptime(str(deadline_val), '%d.%m.%Y')
                deadline_val = int(dt.timestamp())
            elif re.match(r'\d{4}-\d{2}-\d{2}', str(deadline_val)):
                dt = _dt.strptime(str(deadline_val), '%Y-%m-%d')
                deadline_val = int(dt.timestamp())
        except Exception:
            deadline_val = None
        if deadline_val:
            custom_fields.append({"field_id": FIELD_DEADLINE, "values": [{"value": deadline_val}]})
    # Направление (select) — нужно точное значение из enum
    if result.get("direction"):
        direction_raw = str(result["direction"]).strip()
        direction_enum = DIRECTION_ENUM_MAP.get(direction_raw)
        if not direction_enum:
            # Попробуем найти по началу строки
            for key, val in DIRECTION_ENUM_MAP.items():
                if direction_raw.upper().startswith(key):
                    direction_enum = val
                    break
        if direction_enum:
            custom_fields.append({"field_id": FIELD_DIRECTION, "values": [{"value": direction_enum}]})
    # Приоритет (select) — нужно точное значение из enum
    if result.get("priority"):
        priority_raw = str(result["priority"]).strip().upper()
        priority_enum = PRIORITY_ENUM_MAP.get(priority_raw)
        if not priority_enum:
            # Попробуем найти по Р1/Р2/Р3/Р4
            for key, val in PRIORITY_ENUM_MAP.items():
                if key in priority_raw:
                    priority_enum = val
                    break
        if priority_enum:
            custom_fields.append({"field_id": FIELD_PRIORITY, "values": [{"value": priority_enum}]})
    # Источник (select) — "Тендерная площадка" для YaDisk
    custom_fields.append({"field_id": FIELD_SOURCE, "values": [{"value": "\u0422\u0435\u043d\u0434\u0435\u0440\u043d\u0430\u044f \u043f\u043b\u043e\u0449\u0430\u0434\u043a\u0430"}]})
    # Ссылка на папку (url)
    yadisk_url = f"https://disk.yandex.ru/client{folder_path}"
    custom_fields.append({"field_id": FIELD_DOCS_URL, "values": [{"value": yadisk_url}]})
    # Уверенность LLM (numeric: 0-100)
    validation_status = result.get("validation_status", "unknown")
    confidence_map = {"ok": 90, "partial": 60, "blocked": 30, "unknown": 0}
    confidence_score = confidence_map.get(validation_status, 0)
    custom_fields.append({"field_id": FIELD_LLM_CONFIDENCE, "values": [{"value": confidence_score}]})
    # LLM комментарий (textarea) — статус валидации + warnings
    llm_comment_parts = [f"validation: {validation_status}"]
    if result.get("warnings"):
        llm_comment_parts.append(f"warnings: {', '.join(result['warnings'])}")
    custom_fields.append({"field_id": FIELD_LLM_COMMENT, "values": [{"value": "\n".join(llm_comment_parts)}]})

    lead_data = {
        "name": lead_name,
        "pipeline_id": AMO_PIPELINE_ACTIVE,
        "status_id": AMO_STATUS_LLM,
        "custom_fields_values": custom_fields,
    }
    if AMO_USER_RESPONSIBLE:
        lead_data["responsible_user_id"] = AMO_USER_RESPONSIBLE

    try:
        resp = requests.post(
            f"{AMO_BASE_URL}/leads",
            json=[lead_data],
            headers=AMO_HEADERS,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            leads = resp.json().get("_embedded", {}).get("leads", [])
            if leads:
                lead_id = leads[0]["id"]
                logger.info(f"  📋 Сделка создана: ID={lead_id}, name='{lead_name}'")
                return lead_id
        logger.error(f"Ошибка создания сделки: {resp.status_code} {resp.text[:300]}")
    except Exception as e:
        logger.error(f"Исключение при создании сделки: {e}")
    return None


# ═════════════════════════════════════════════════════════════════
# ОСНОВНАЯ ФУНКЦИЯ (CRON)
# ═══════════════════════════════════════════════════════════════════

def run_yadisk_scan(dry_run: bool = True) -> dict:
    """
    Основная функция — запускается каждый час.
    
    Пайплайн:
    1. Сканирует Яндекс.Диск
    2. Для каждого тендера скачивает файлы и вычисляет хеши
    3. Проверяет дедупликацию (хеши + fuzzy)
    4. По результату:
       - Новый → LLM-классификация → создание сделки
       - Дубль → игнорирование + заметка
       - Обогащение → обновление карточки + заметка
       - Обновление → перезапуск LLM + обновление карточки
       - Fuzzy-дубль → создание сделки + предупреждение
    5. Валидация полей после создания/обновления
    
    Args:
        dry_run: если True — только сканирование, без создания сделок
        
    Returns:
        Статистика: {new, duplicates, enriched, updated, fuzzy, errors}
    """
    if not YADISK_TOKEN:
        logger.error("YADISK_TOKEN не задан в .env")
        return {"error": "YADISK_TOKEN not configured"}

    # Импортируем дедупликатор
    from .deduplication import (
        TenderDeduplicator, DeduplicationDB, FileRecord,
        compute_file_hash, format_enrichment_note,
    )

    client = YaDiskClient()
    conn = init_db()
    dedup_db = DeduplicationDB(DB_PATH)
    deduplicator = TenderDeduplicator(dedup_db)

    stats = {
        "total_scanned": 0,
        "new": 0,
        "duplicates": 0,
        "enriched": 0,
        "updated": 0,
        "fuzzy": 0,
        "errors": 0,
        "skipped": 0,
        "details": [],
    }

    try:
        all_tenders = scan_root_folder(client)
        stats["total_scanned"] = len(all_tenders)

        for tender in all_tenders:
            folder_path = tender["folder_path"]
            folder_name = tender["folder_name"]
            date_folder = tender["date_folder"]
            files = tender["files"]

            total_size = sum(f["size"] for f in files)

            # ─── Скачивание файлов для хеширования ───────────────
            tmp_dir = tempfile.mkdtemp(prefix=f"tender_dedup_")
            downloaded_files = []
            file_records = []

            for file_info in files:
                local_name = os.path.basename(file_info["path"])
                local_path = os.path.join(tmp_dir, local_name)

                if client.download_file(file_info["path"], local_path):
                    downloaded_files.append(local_path)
                    # Вычисляем хеш
                    file_hash = compute_file_hash(local_path)
                    file_records.append(FileRecord(
                        filename=local_name,
                        file_hash=file_hash,
                        file_size=file_info["size"],
                        file_path=file_info["path"],
                    ))

            if not file_records:
                logger.warning(f"Не удалось скачать файлы: {folder_name}")
                stats["errors"] += 1
                continue

            # ─── Дедупликация ────────────────────────────────────
            # Извлекаем заказчика из имени папки (простая эвристика)
            customer_hint = _extract_customer_from_folder_name(folder_name)

            dedup_result = deduplicator.check(
                tender_path=folder_path,
                files=file_records,
                customer=customer_hint,
                nmc=0,  # НМЦ пока неизвестна до LLM
            )

            # ─── Обработка по типу ───────────────────────────────
            if dedup_result.is_exact_duplicate:
                # 100% дубль — игнорируем
                stats["duplicates"] += 1
                if dedup_result.existing_lead_id and not dry_run:
                    _post_note_to_lead(
                        dedup_result.existing_lead_id,
                        dedup_result.message
                    )
                stats["details"].append({
                    "name": folder_name,
                    "date": date_folder,
                    "action": "duplicate_ignored",
                    "existing_lead": dedup_result.existing_lead_id,
                })
                logger.info(f"  ⏭️ Дубль: {folder_name}")
                continue

            elif dedup_result.is_enrichment:
                # Обогащение — обновляем карточку
                stats["enriched"] += 1

                if not dry_run and dedup_result.existing_lead_id:
                    # Распаковываем архивы
                    all_files = extract_archives(downloaded_files, tmp_dir)

                    # Перезапускаем LLM только на новых файлах
                    new_file_paths = [
                        f for f in all_files
                        if os.path.basename(f) in dedup_result.new_files
                    ]

                    # Пишем заметку об обогащении
                    note_text = format_enrichment_note(dedup_result)
                    _post_note_to_lead(dedup_result.existing_lead_id, note_text)

                    # Обновляем хеши в базе
                    dedup_db.save_tender(
                        tender_path=folder_path,
                        files=file_records,
                        lead_id=dedup_result.existing_lead_id,
                    )

                    # TODO: Перезапуск LLM на новых файлах для обновления полей

                stats["details"].append({
                    "name": folder_name,
                    "date": date_folder,
                    "action": "enriched",
                    "new_files": dedup_result.new_files,
                    "existing_lead": dedup_result.existing_lead_id,
                })
                logger.info(
                    f"  📎 Обогащение: {folder_name} "
                    f"(+{len(dedup_result.new_files)} файлов)"
                )
                continue

            elif dedup_result.is_update:
                # Обновление файлов — перезапускаем анализ
                stats["updated"] += 1

                if not dry_run and dedup_result.existing_lead_id:
                    all_files = extract_archives(downloaded_files, tmp_dir)

                    # Пишем заметку
                    _post_note_to_lead(
                        dedup_result.existing_lead_id,
                        dedup_result.message
                    )

                    # Обновляем хеши
                    dedup_db.save_tender(
                        tender_path=folder_path,
                        files=file_records,
                        lead_id=dedup_result.existing_lead_id,
                    )

                    # TODO: Перезапуск LLM для обновления классификации

                stats["details"].append({
                    "name": folder_name,
                    "date": date_folder,
                    "action": "updated",
                    "updated_files": dedup_result.updated_files,
                    "existing_lead": dedup_result.existing_lead_id,
                })
                logger.info(
                    f"  🔄 Обновление: {folder_name} "
                    f"({len(dedup_result.updated_files)} файлов изменились)"
                )
                continue

            elif dedup_result.is_fuzzy_duplicate:
                # Fuzzy-дубль — создаём отдельную карточку с предупреждением
                stats["fuzzy"] += 1
                logger.info(
                    f"  ⚠️ Fuzzy-дубль: {folder_name} "
                    f"(score={dedup_result.match_score:.2f})"
                )
                # Продолжаем как новый тендер, но с предупреждением
                # (не делаем continue — пойдёт дальше в обработку нового)

            # ─── Новый тендер (или fuzzy-дубль) ──────────────────
            stats["new"] += 1
            logger.info(f"  🆕 Новый: {folder_name} ({len(files)} файлов)")

            # Распаковка ZIP
            all_files = extract_archives(downloaded_files, tmp_dir)

            # Записываем в legacy DB
            mark_tender_processed(
                conn, folder_path, folder_name, date_folder,
                file_count=len(files), total_size=total_size,
                status="pending"
            )

            if dry_run:
                update_tender_status(conn, folder_path, status="dry_run")
                # Сохраняем хеши для будущей дедупликации
                dedup_db.save_tender(
                    tender_path=folder_path,
                    files=file_records,
                    customer=customer_hint,
                    date_folder=date_folder,
                )
                stats["details"].append({
                    "name": folder_name,
                    "date": date_folder,
                    "files": len(files),
                    "size_kb": round(total_size / 1024),
                    "action": "dry_run",
                    "is_fuzzy": dedup_result.is_fuzzy_duplicate,
                })
                continue

            # ─── Быстрая экстракция + парсинг (вместо медленной LLM) ───────────────
            try:
                import sys
                project_root = Path(__file__).parent.parent.parent
                scripts_dir = project_root / "scripts"
                if str(scripts_dir) not in sys.path:
                    sys.path.append(str(scripts_dir))
                
                import extract_and_classify as ec_module
                
                # 1. Извлекаем текст из всех файлов
                all_text = ""
                for f in all_files:
                    if os.path.exists(f):
                        text = ec_module.extract_file(f)
                        if isinstance(text, tuple):
                            text = text[0]
                        all_text += text + "\n"
                
                # 2. Парсим поля
                parsed = ec_module.parse_tender_fields(all_text, all_files)
                
                # 3. Валидация + OCR fallback
                pdf_files_list = [f for f in all_files if f.lower().endswith('.pdf')]
                parsed = ec_module.validate_and_ocr_fallback(parsed, pdf_files_list, all_text)
                
                # Маппинг результата в старый формат для обратной совместимости
                result = {
                    "customer": parsed.get("customer") or customer_hint,
                    "nmc": parsed.get("nmc") or 0,
                    "direction": parsed.get("direction_hint") or "CARBIDE-STANDARD",
                    "deadline": parsed.get("deadline") or "",
                    "priority": parsed.get("priority_hint") or "P3",
                    "validation_status": parsed.get("validation_status") or "unknown",
                    "confidence": parsed.get("confidence_scores") or {}
                }

                # Сохраняем в dedup DB с данными от парсера
                dedup_db.save_tender(
                    tender_path=folder_path,
                    files=file_records,
                    customer=result.get("customer"),
                    nmc=result.get("nmc"),
                    direction=result.get("direction"),
                    date_folder=date_folder,
                )

                update_tender_status(
                    conn, folder_path,
                    status="classified",
                    llm_result=json.dumps(result, ensure_ascii=False),
                )

                # Если fuzzy-дубль — добавляем предупреждение
                if dedup_result.is_fuzzy_duplicate:
                    result["_fuzzy_warning"] = dedup_result.message

                # ─── Создание сделки в amoCRM ────────────────────
                lead_id = None
                if result.get("customer"):
                    lead_id = _create_amo_lead(result, folder_name, folder_path, date_folder)
                    if lead_id:
                        update_tender_status(
                            conn, folder_path,
                            status="lead_created",
                            amo_lead_id=lead_id,
                            llm_result=json.dumps(result, ensure_ascii=False),
                        )
                        dedup_db.update_lead_id(folder_path, lead_id)
                        # Добавляем заметку со списком файлов
                        files_note = f"📁 Папка: {folder_path}\n"
                        files_note += f"📅 Дата: {date_folder}\n"
                        files_note += f"📊 Файлов: {len(files)}\n"
                        if result.get('validation_status') != 'ok':
                            files_note += f"⚠️ Статус валидации: {result['validation_status']}\n"
                        if dedup_result.is_fuzzy_duplicate:
                            files_note += f"⚠️ Fuzzy-дубль: {dedup_result.message}\n"
                        _post_note_to_lead(lead_id, files_note)
                        stats["leads_created"] = stats.get("leads_created", 0) + 1
                else:
                    logger.warning(f"  ⚠️ Заказчик не определён — сделка НЕ создана (folder: {folder_name})")

                stats["details"].append({
                    "name": folder_name,
                    "date": date_folder,
                    "files": len(files),
                    "action": "classified",
                    "result": result,
                    "is_fuzzy": dedup_result.is_fuzzy_duplicate,
                    "lead_id": lead_id,
                })
                
                logger.info(f"  ✅ Парсинг завершён: статус {result['validation_status']}, заказчик {result['customer']}, lead_id={lead_id}")

            except ImportError as e:
                logger.error(f"Не удалось импортировать extract_and_classify: {e}")
                update_tender_status(conn, folder_path, status="awaiting_llm")
                dedup_db.save_tender(
                    tender_path=folder_path,
                    files=file_records,
                    customer=customer_hint,
                    date_folder=date_folder,
                )
                stats["details"].append({
                    "name": folder_name,
                    "date": date_folder,
                    "files": len(files),
                    "action": "awaiting_llm",
                })

            except Exception as e:
                logger.error(f"Ошибка парсинга для {folder_name}: {e}")
                update_tender_status(conn, folder_path, status="error", error=str(e))
                stats["errors"] += 1

    except Exception as e:
        logger.error(f"Критическая ошибка сканирования: {e}")
        stats["errors"] += 1

    finally:
        conn.close()

    logger.info(
        f"Итог: всего={stats['total_scanned']}, "
        f"новых={stats['new']}, дублей={stats['duplicates']}, "
        f"обогащено={stats['enriched']}, обновлено={stats['updated']}, "
        f"fuzzy={stats['fuzzy']}, ошибок={stats['errors']}"
    )
    return stats


# ═══════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════════

def _extract_customer_from_folder_name(folder_name: str) -> str:
    """
    Попытаться извлечь название заказчика из имени папки тендера.
    
    Примеры:
    - "АО НПП ИСТОК ШОКИНА - Не интересно - Калибры" → "АО НПП ИСТОК ШОКИНА"
    - "Gesac - 86 поз." → "Gesac"
    - "АО ОКБ ФАКЕЛ - твердосплав 350к руб" → "АО ОКБ ФАКЕЛ"
    """
    # Разделяем по " - " и берём первую часть
    parts = folder_name.split(" - ")
    if parts:
        return parts[0].strip()
    return folder_name.strip()


# ═══════════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    dry_run = os.getenv("DRY_RUN", "1") == "1"
    result = run_yadisk_scan(dry_run=dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
"""
"""
