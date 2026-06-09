"""
Модуль дедупликации и обогащения тендеров.

Сценарии:
1. 100% дубль — хеши всех файлов совпадают → игнорируем
2. Обогащение — часть файлов совпадает + есть новые → обновляем карточку
3. Обновление — файл с тем же именем, но другой хеш → перезапускаем анализ
4. Fuzzy-дубль — другая папка, но тот же заказчик+НМЦ → предупреждаем

Хранение: SQLite таблица `tender_files` с хешами.
"""

import hashlib
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# МОДЕЛИ ДАННЫХ
# ═══════════════════════════════════════════════════════════════════

@dataclass
class FileRecord:
    """Запись о файле тендера."""
    filename: str
    file_hash: str
    file_size: int
    file_path: str  # Путь на Яндекс.Диске


@dataclass
class DeduplicationResult:
    """Результат проверки на дубль."""
    # Тип результата
    is_new: bool = False           # Полностью новый тендер
    is_exact_duplicate: bool = False  # 100% дубль (все хеши совпадают)
    is_enrichment: bool = False    # Обогащение (есть новые файлы)
    is_update: bool = False        # Обновление (файл изменился)
    is_fuzzy_duplicate: bool = False  # Fuzzy-дубль (похожий тендер)

    # Ссылка на существующую карточку
    existing_lead_id: Optional[int] = None
    existing_tender_path: Optional[str] = None

    # Детали
    new_files: list = field(default_factory=list)      # Новые файлы
    updated_files: list = field(default_factory=list)  # Обновлённые файлы
    unchanged_files: list = field(default_factory=list)  # Без изменений
    match_score: float = 0.0       # Оценка совпадения (0.0-1.0)
    message: str = ""              # Сообщение для ленты


# ═══════════════════════════════════════════════════════════════════
# ХЕШИРОВАНИЕ ФАЙЛОВ
# ═══════════════════════════════════════════════════════════════════

def compute_file_hash(file_path: str) -> str:
    """Вычислить SHA-256 хеш файла."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (IOError, OSError) as e:
        logger.error(f"Ошибка хеширования {file_path}: {e}")
        return ""


def compute_content_hash(content: bytes) -> str:
    """Вычислить SHA-256 хеш из байтов (для скачанных файлов)."""
    return hashlib.sha256(content).hexdigest()


# ═══════════════════════════════════════════════════════════════════
# FUZZY MATCHING
# ═══════════════════════════════════════════════════════════════════

def normalize_customer_name(name: str) -> str:
    """Нормализовать название заказчика для сравнения."""
    if not name:
        return ""
    # Убираем типичные префиксы/суффиксы
    noise = [
        "АО", "ОАО", "ПАО", "ООО", "ЗАО", "ФГУП", "ГУП",
        "им.", "имени", "«", "»", '"', "'",
        "Филиал", "Представительство",
    ]
    result = name.upper().strip()
    for word in noise:
        result = result.replace(word.upper(), "")
    # Убираем лишние пробелы
    result = " ".join(result.split())
    return result.strip()


def customer_similarity(name1: str, name2: str) -> float:
    """Оценить схожесть двух названий заказчиков (0.0-1.0)."""
    n1 = normalize_customer_name(name1)
    n2 = normalize_customer_name(name2)
    if not n1 or not n2:
        return 0.0
    return SequenceMatcher(None, n1, n2).ratio()


def nmc_similarity(nmc1: float, nmc2: float, tolerance: float = 0.05) -> bool:
    """Проверить совпадение НМЦ с допуском ±5%."""
    if nmc1 <= 0 or nmc2 <= 0:
        return False
    ratio = min(nmc1, nmc2) / max(nmc1, nmc2)
    return ratio >= (1.0 - tolerance)


# ═══════════════════════════════════════════════════════════════════
# БАЗА ДАННЫХ
# ═══════════════════════════════════════════════════════════════════

class DeduplicationDB:
    """SQLite хранилище для дедупликации."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "data", "processed_tenders.db"
            )
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Инициализировать таблицы."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tender_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tender_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    lead_id INTEGER,
                    customer TEXT,
                    nmc REAL DEFAULT 0,
                    position_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tender_path, filename)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tender_meta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tender_path TEXT UNIQUE NOT NULL,
                    lead_id INTEGER,
                    customer TEXT,
                    customer_normalized TEXT,
                    nmc REAL DEFAULT 0,
                    position_count INTEGER DEFAULT 0,
                    direction TEXT,
                    date_folder TEXT,
                    status TEXT DEFAULT 'active',
                    file_count INTEGER DEFAULT 0,
                    total_hash TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tender_meta_customer
                ON tender_meta(customer_normalized)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tender_files_hash
                ON tender_files(file_hash)
            """)
            conn.commit()

    def get_tender_meta(self, tender_path: str) -> Optional[dict]:
        """Получить метаданные тендера по пути."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM tender_meta WHERE tender_path = ?",
                (tender_path,)
            ).fetchone()
            return dict(row) if row else None

    def get_tender_files(self, tender_path: str) -> list:
        """Получить все файлы тендера."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM tender_files WHERE tender_path = ?",
                (tender_path,)
            ).fetchall()
            return [dict(r) for r in rows]

    def find_similar_tenders(
        self, customer: str, nmc: float, exclude_path: str = None
    ) -> list:
        """Найти похожие тендеры по заказчику и НМЦ."""
        customer_norm = normalize_customer_name(customer)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Получаем все тендеры для fuzzy-сравнения
            query = "SELECT * FROM tender_meta WHERE status = 'active'"
            params = []
            if exclude_path:
                query += " AND tender_path != ?"
                params.append(exclude_path)
            rows = conn.execute(query, params).fetchall()

        results = []
        for row in rows:
            row_dict = dict(row)
            score = 0.0
            matches = 0

            # Сравнение заказчика
            cust_sim = customer_similarity(customer, row_dict.get("customer", ""))
            if cust_sim >= 0.7:
                score += cust_sim * 0.4
                matches += 1

            # Сравнение НМЦ
            if nmc > 0 and row_dict.get("nmc", 0) > 0:
                if nmc_similarity(nmc, row_dict["nmc"]):
                    score += 0.3
                    matches += 1

            # Если совпадает хотя бы заказчик с высокой точностью
            if matches >= 1 and score >= 0.3:
                row_dict["match_score"] = score
                row_dict["customer_similarity"] = cust_sim
                results.append(row_dict)

        # Сортируем по score
        results.sort(key=lambda x: x["match_score"], reverse=True)
        return results

    def find_by_file_hash(self, file_hash: str) -> list:
        """Найти тендеры содержащие файл с данным хешем."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT DISTINCT tender_path, lead_id FROM tender_files WHERE file_hash = ?",
                (file_hash,)
            ).fetchall()
            return [dict(r) for r in rows]

    def save_tender(
        self,
        tender_path: str,
        files: list,
        lead_id: int = None,
        customer: str = None,
        nmc: float = 0,
        position_count: int = 0,
        direction: str = None,
        date_folder: str = None,
    ):
        """Сохранить тендер и его файлы."""
        customer_norm = normalize_customer_name(customer) if customer else ""
        # Вычислить общий хеш (сортированная конкатенация хешей файлов)
        sorted_hashes = sorted([f.file_hash for f in files if f.file_hash])
        total_hash = hashlib.sha256("".join(sorted_hashes).encode()).hexdigest()

        with sqlite3.connect(self.db_path) as conn:
            # Upsert tender_meta
            conn.execute("""
                INSERT INTO tender_meta 
                    (tender_path, lead_id, customer, customer_normalized, nmc, 
                     position_count, direction, date_folder, file_count, total_hash, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tender_path) DO UPDATE SET
                    lead_id = COALESCE(excluded.lead_id, tender_meta.lead_id),
                    customer = COALESCE(excluded.customer, tender_meta.customer),
                    customer_normalized = COALESCE(excluded.customer_normalized, tender_meta.customer_normalized),
                    nmc = CASE WHEN excluded.nmc > 0 THEN excluded.nmc ELSE tender_meta.nmc END,
                    position_count = CASE WHEN excluded.position_count > 0 THEN excluded.position_count ELSE tender_meta.position_count END,
                    direction = COALESCE(excluded.direction, tender_meta.direction),
                    file_count = excluded.file_count,
                    total_hash = excluded.total_hash,
                    updated_at = excluded.updated_at
            """, (
                tender_path, lead_id, customer, customer_norm, nmc,
                position_count, direction, date_folder, len(files),
                total_hash, datetime.now().isoformat()
            ))

            # Upsert files
            for f in files:
                conn.execute("""
                    INSERT INTO tender_files 
                        (tender_path, filename, file_hash, file_size, lead_id, customer, nmc, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tender_path, filename) DO UPDATE SET
                        file_hash = excluded.file_hash,
                        file_size = excluded.file_size,
                        lead_id = COALESCE(excluded.lead_id, tender_files.lead_id),
                        updated_at = excluded.updated_at
                """, (
                    tender_path, f.filename, f.file_hash, f.file_size,
                    lead_id, customer, nmc, datetime.now().isoformat()
                ))
            conn.commit()

    def update_lead_id(self, tender_path: str, lead_id: int):
        """Обновить lead_id для тендера после создания сделки."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tender_meta SET lead_id = ?, updated_at = ? WHERE tender_path = ?",
                (lead_id, datetime.now().isoformat(), tender_path)
            )
            conn.execute(
                "UPDATE tender_files SET lead_id = ? WHERE tender_path = ?",
                (lead_id, tender_path)
            )
            conn.commit()


# ═══════════════════════════════════════════════════════════════════
# ОСНОВНАЯ ЛОГИКА ДЕДУПЛИКАЦИИ
# ═══════════════════════════════════════════════════════════════════

class TenderDeduplicator:
    """Дедупликатор тендеров."""

    def __init__(self, db: DeduplicationDB = None):
        self.db = db or DeduplicationDB()

    def check(
        self,
        tender_path: str,
        files: list,
        customer: str = None,
        nmc: float = 0,
    ) -> DeduplicationResult:
        """
        Проверить тендер на дубликат.

        Args:
            tender_path: Путь к папке тендера на Яндекс.Диске
            files: Список FileRecord с хешами файлов
            customer: Название заказчика (из LLM или из имени папки)
            nmc: НМЦ (если известна)

        Returns:
            DeduplicationResult с типом и деталями
        """
        result = DeduplicationResult()

        # ─── Шаг 1: Проверка по точному пути (повторная загрузка) ───
        existing_meta = self.db.get_tender_meta(tender_path)
        if existing_meta:
            return self._check_same_path(tender_path, files, existing_meta)

        # ─── Шаг 2: Проверка по хешам файлов (те же файлы, другая папка) ───
        hash_match = self._check_file_hashes(files, tender_path)
        if hash_match:
            return hash_match

        # ─── Шаг 3: Fuzzy-match по заказчику + НМЦ ───
        if customer:
            fuzzy_match = self._check_fuzzy(tender_path, customer, nmc)
            if fuzzy_match:
                return fuzzy_match

        # ─── Шаг 4: Новый тендер ───
        result.is_new = True
        result.new_files = [f.filename for f in files]
        result.message = f"🆕 Новый тендер: {len(files)} файлов"
        logger.info(f"[DEDUP] Новый тендер: {tender_path} ({len(files)} файлов)")
        return result

    def _check_same_path(
        self, tender_path: str, files: list, existing_meta: dict
    ) -> DeduplicationResult:
        """Проверка при повторной загрузке из той же папки."""
        result = DeduplicationResult()
        result.existing_lead_id = existing_meta.get("lead_id")
        result.existing_tender_path = tender_path

        # Получаем существующие файлы
        existing_files = self.db.get_tender_files(tender_path)
        existing_by_name = {f["filename"]: f for f in existing_files}
        existing_hashes = {f["file_hash"] for f in existing_files}

        new_files = []
        updated_files = []
        unchanged_files = []

        for f in files:
            if f.filename in existing_by_name:
                existing = existing_by_name[f.filename]
                if f.file_hash == existing["file_hash"]:
                    unchanged_files.append(f.filename)
                else:
                    updated_files.append(f.filename)
            else:
                # Файл с новым именем — проверяем хеш
                if f.file_hash in existing_hashes:
                    # Тот же файл, переименован
                    unchanged_files.append(f.filename)
                else:
                    new_files.append(f.filename)

        result.new_files = new_files
        result.updated_files = updated_files
        result.unchanged_files = unchanged_files

        # Определяем тип
        if not new_files and not updated_files:
            # 100% дубль
            result.is_exact_duplicate = True
            result.message = "📎 Дубль проигнорирован — файлы идентичны"
            logger.info(f"[DEDUP] 100% дубль: {tender_path}")
        elif updated_files and not new_files:
            # Обновление существующих файлов
            result.is_update = True
            result.message = (
                f"📎 Обновлённые файлы обнаружены. Перезапускаю анализ.\n"
                f"Обновлены: {', '.join(updated_files)}"
            )
            logger.info(f"[DEDUP] Обновление: {tender_path}, файлы: {updated_files}")
        else:
            # Обогащение (новые файлы)
            result.is_enrichment = True
            parts = []
            if new_files:
                parts.append(f"Добавлены: {', '.join(new_files)}")
            if updated_files:
                parts.append(f"Обновлены: {', '.join(updated_files)}")
            result.message = (
                f"📎 Дубль обнаружен → карточка обогащена\n" +
                "\n".join(parts)
            )
            logger.info(
                f"[DEDUP] Обогащение: {tender_path}, "
                f"новые: {new_files}, обновлены: {updated_files}"
            )

        return result

    def _check_file_hashes(
        self, files: list, current_path: str
    ) -> Optional[DeduplicationResult]:
        """Проверка по хешам файлов (те же файлы в другой папке)."""
        if not files:
            return None

        # Проверяем каждый файл
        hash_matches = {}  # tender_path → count of matching files
        for f in files:
            if not f.file_hash:
                continue
            matches = self.db.find_by_file_hash(f.file_hash)
            for m in matches:
                path = m["tender_path"]
                if path != current_path:
                    hash_matches[path] = hash_matches.get(path, 0) + 1

        if not hash_matches:
            return None

        # Находим лучшее совпадение
        best_path = max(hash_matches, key=hash_matches.get)
        match_count = hash_matches[best_path]
        match_ratio = match_count / len(files)

        if match_ratio >= 0.8:  # 80%+ файлов совпадают
            result = DeduplicationResult()
            existing_meta = self.db.get_tender_meta(best_path)
            result.existing_lead_id = existing_meta.get("lead_id") if existing_meta else None
            result.existing_tender_path = best_path
            result.match_score = match_ratio

            if match_ratio >= 1.0:
                result.is_exact_duplicate = True
                result.message = (
                    f"📎 Полный дубль (другая папка).\n"
                    f"Оригинал: {best_path}\n"
                    f"Совпадение: {match_count}/{len(files)} файлов"
                )
            else:
                result.is_enrichment = True
                result.message = (
                    f"📎 Частичный дубль обнаружен.\n"
                    f"Оригинал: {best_path}\n"
                    f"Совпадение: {match_count}/{len(files)} файлов.\n"
                    f"Обогащаю карточку новыми файлами."
                )

            logger.info(
                f"[DEDUP] Hash-match: {current_path} → {best_path} "
                f"({match_count}/{len(files)} = {match_ratio:.0%})"
            )
            return result

        return None

    def _check_fuzzy(
        self, tender_path: str, customer: str, nmc: float
    ) -> Optional[DeduplicationResult]:
        """Fuzzy-match по заказчику и НМЦ."""
        similar = self.db.find_similar_tenders(customer, nmc, exclude_path=tender_path)

        if not similar:
            return None

        best = similar[0]
        if best["match_score"] >= 0.6:
            result = DeduplicationResult()
            result.is_fuzzy_duplicate = True
            result.existing_lead_id = best.get("lead_id")
            result.existing_tender_path = best.get("tender_path")
            result.match_score = best["match_score"]
            result.message = (
                f"⚠️ Возможный дубль!\n"
                f"Похожий тендер: {best.get('tender_path')}\n"
                f"Заказчик: {best.get('customer')} "
                f"(совпадение: {best.get('customer_similarity', 0):.0%})\n"
                f"НМЦ: {best.get('nmc', 0):,.0f} руб.\n\n"
                f"Создаю отдельную карточку, но проверьте — возможно это дубль."
            )
            logger.info(
                f"[DEDUP] Fuzzy-match: {tender_path} ≈ {best['tender_path']} "
                f"(score={best['match_score']:.2f})"
            )
            return result

        return None


# ═══════════════════════════════════════════════════════════════════
# ФОРМИРОВАНИЕ СООБЩЕНИЙ ДЛЯ ЛЕНТЫ amoCRM
# ═══════════════════════════════════════════════════════════════════

def format_enrichment_note(
    result: DeduplicationResult,
    old_fields: dict = None,
    new_fields: dict = None,
) -> str:
    """Сформировать заметку об обогащении для ленты amoCRM."""
    parts = [result.message, ""]

    # Если есть изменения полей
    if old_fields and new_fields:
        changes = []
        for key, new_val in new_fields.items():
            old_val = old_fields.get(key)
            if old_val != new_val and new_val:
                changes.append(f"  • {key}: {old_val} → {new_val}")
        if changes:
            parts.append("Обновлены поля:")
            parts.extend(changes)
            parts.append("")

    # Без изменений
    if result.unchanged_files:
        parts.append(f"Без изменений: {len(result.unchanged_files)} файлов")

    parts.append(f"\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(parts)
