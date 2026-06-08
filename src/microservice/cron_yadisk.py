"""
Модуль опроса Яндекс.Диска — cron_yadisk.py

Запускается каждый час. Логика:
1. Обходит папку YADISK_ROOT_FOLDER (по умолчанию /ТОРГИ)
2. Ищет папки с датами (DD.MM.YYYY) — это дни загрузки
3. Внутри каждой даты — папки тендеров (название = описание тендера)
4. Внутри тендера — файлы (.xlsx, .docx, .doc, .pdf, .zip и т.д.)
5. Может быть ещё одна вложенность (подпапка с любым названием)
6. Дедупликация через SQLite: каждая папка тендера обрабатывается один раз
7. Новые тендеры отправляются в LLM-классификатор → создаётся сделка в amoCRM

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

# SQLite для дедупликации
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


# ═══════════════════════════════════════════════════════════════════
# SQLITE: ДЕДУПЛИКАЦИЯ
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
    """Проверить, был ли тендер уже обработан."""
    cursor = conn.execute(
        "SELECT id FROM processed_tenders WHERE folder_path = ?",
        (folder_path,)
    )
    return cursor.fetchone() is not None


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
    
    Возвращает список новых (необработанных) тендеров:
    [
        {
            "folder_path": "/ТОРГИ/09.06.2026/Gesac - 86 поз.",
            "folder_name": "Gesac - 86 поз.",
            "date_folder": "09.06.2026",
            "files": [
                {"name": "file.xlsx", "path": "/ТОРГИ/.../file.xlsx", "size": 1234, "mime_type": "..."},
                ...
            ]
        },
        ...
    ]
    """
    conn = init_db()
    new_tenders = []

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

            # Проверка дедупликации
            if is_tender_processed(conn, tender_path):
                continue

            # Уровень 3: файлы тендера (+ возможная подпапка)
            files = collect_files_recursive(client, tender_path, depth=0)

            if not files:
                logger.debug(f"    Пропуск (нет файлов): {tender_name}")
                continue

            new_tenders.append({
                "folder_path": tender_path,
                "folder_name": tender_name,
                "date_folder": date_name,
                "files": files,
            })

    conn.close()
    logger.info(f"Найдено {len(new_tenders)} новых тендеров для обработки")
    return new_tenders


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
    распаковывает их и возвращает обновлённый список файлов
    (архивы заменены на их содержимое).

    Поддерживает:
    - .zip (включая вложенные zip-в-zip, 1 уровень)
    - Фильтрацию по расширению (только полезные файлы)
    - Защиту от zip-бомб (макс 100 файлов, макс 500 MB)
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
                # Не удалось распаковать — оставляем архив как есть
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
    """
    Распаковать ZIP-архив во временную папку.

    Защита:
    - Максимум max_files файлов из одного архива
    - Максимум max_total_bytes суммарно
    - Игнорирует path traversal (файлы с ../)
    - Игнорирует скрытые файлы (._*, __MACOSX, ~$*)
    - Вложенные zip тоже распаковываются (1 уровень)
    """
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

            # Защита от zip-бомб
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

                # Извлекаем файл (плоская структура — все в одну папку)
                out_path = os.path.join(out_dir, basename)

                # Если файл с таким именем уже есть — добавляем суффикс
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
# ОСНОВНАЯ ФУНКЦИЯ (CRON)
# ═══════════════════════════════════════════════════════════════════

def run_yadisk_scan(dry_run: bool = True) -> dict:
    """
    Основная функция — запускается каждый час.
    
    1. Сканирует Яндекс.Диск
    2. Находит новые тендеры
    3. Скачивает файлы во временную папку
    4. Отправляет в LLM-классификатор (если подключён)
    5. Создаёт сделки в amoCRM
    
    Args:
        dry_run: если True — только сканирование, без создания сделок
        
    Returns:
        Статистика: {new_tenders, processed, errors, skipped}
    """
    if not YADISK_TOKEN:
        logger.error("YADISK_TOKEN не задан в .env")
        return {"error": "YADISK_TOKEN not configured"}

    client = YaDiskClient()
    conn = init_db()

    stats = {
        "new_tenders": 0,
        "processed": 0,
        "errors": 0,
        "skipped": 0,
        "details": [],
    }

    try:
        new_tenders = scan_root_folder(client)
        stats["new_tenders"] = len(new_tenders)

        for tender in new_tenders:
            folder_path = tender["folder_path"]
            folder_name = tender["folder_name"]
            date_folder = tender["date_folder"]
            files = tender["files"]

            total_size = sum(f["size"] for f in files)

            logger.info(f"Обработка: {folder_name} ({len(files)} файлов, {total_size / 1024:.0f} KB)")

            # Записываем как pending
            tender_id = mark_tender_processed(
                conn, folder_path, folder_name, date_folder,
                file_count=len(files), total_size=total_size,
                status="pending"
            )

            if dry_run:
                update_tender_status(conn, folder_path, status="dry_run")
                stats["processed"] += 1
                stats["details"].append({
                    "name": folder_name,
                    "date": date_folder,
                    "files": len(files),
                    "size_kb": round(total_size / 1024),
                    "status": "dry_run",
                })
                continue

            # ─── Скачивание файлов ───────────────────────────────
            tmp_dir = tempfile.mkdtemp(prefix=f"tender_{tender_id}_")
            downloaded_files = []

            for file_info in files:
                local_name = os.path.basename(file_info["path"])
                local_path = os.path.join(tmp_dir, local_name)

                if client.download_file(file_info["path"], local_path):
                    downloaded_files.append(local_path)

            # Распаковка ZIP-архивов
            downloaded_files = extract_archives(downloaded_files, tmp_dir)

            if not downloaded_files:
                update_tender_status(conn, folder_path, status="error", error="No files downloaded")
                stats["errors"] += 1
                continue

            # ─── LLM Классификация ───────────────────────────────
            try:
                from .llm_classifier import classify_tender
                result = classify_tender(
                    folder_name=folder_name,
                    date_folder=date_folder,
                    files=downloaded_files,
                )
                update_tender_status(
                    conn, folder_path,
                    status="classified",
                    llm_result=json.dumps(result, ensure_ascii=False),
                )
                stats["processed"] += 1
                stats["details"].append({
                    "name": folder_name,
                    "date": date_folder,
                    "files": len(files),
                    "status": "classified",
                    "result": result,
                })
            except ImportError:
                # LLM-модуль ещё не подключён — просто записываем
                update_tender_status(conn, folder_path, status="awaiting_llm")
                stats["processed"] += 1
                stats["details"].append({
                    "name": folder_name,
                    "date": date_folder,
                    "files": len(files),
                    "status": "awaiting_llm",
                })
            except Exception as e:
                logger.error(f"Ошибка LLM для {folder_name}: {e}")
                update_tender_status(conn, folder_path, status="error", error=str(e))
                stats["errors"] += 1

    except Exception as e:
        logger.error(f"Критическая ошибка сканирования: {e}")
        stats["errors"] += 1

    finally:
        conn.close()

    logger.info(
        f"Итог: новых={stats['new_tenders']}, "
        f"обработано={stats['processed']}, "
        f"ошибок={stats['errors']}"
    )
    return stats


# ═══════════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    dry_run = os.getenv("DRY_RUN", "1") == "1"
    result = run_yadisk_scan(dry_run=dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
