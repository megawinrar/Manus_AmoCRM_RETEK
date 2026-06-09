"""
Модуль валидации обязательных полей карточки.

Проверяет что при переходе в определённый статус все обязательные поля заполнены.
Если нет — пишет предупреждение в ленту карточки (внутренний чат).

Может работать:
1. При смене статуса (через webhook) — проверяет поля нового статуса
2. По расписанию (cron) — проверяет все карточки в статусе на заполненность
3. Перед архивацией — блокирует перенос если не заполнены критические поля
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════

AMO_DOMAIN = os.getenv("AMO_DOMAIN", "")
AMO_TOKEN = os.getenv("AMO_ACCESS_TOKEN", "")
HEADERS = {
    "Authorization": f"Bearer {AMO_TOKEN}",
    "Content-Type": "application/json",
}
BASE_URL = f"https://{AMO_DOMAIN}/api/v4"


# ═══════════════════════════════════════════════════════════════════
# ОБЯЗАТЕЛЬНЫЕ ПОЛЯ ПО СТАТУСАМ
# ═══════════════════════════════════════════════════════════════════
# Формат: status_env_key → список (field_id, field_name, severity)
# severity: "block" = блокирует переход, "warn" = только предупреждение

# Импортируем ID полей
FIELD_IDS = {
    "CUSTOMER":         int(os.getenv("FIELD_CUSTOMER", "380299")),
    "DIRECTION":        int(os.getenv("FIELD_DIRECTION", "380311")),
    "PRIORITY":         int(os.getenv("FIELD_PRIORITY", "380309")),
    "SITUATION_TYPE":   int(os.getenv("FIELD_SITUATION_TYPE", "380305")),
    "NMC":              int(os.getenv("FIELD_NMC", "380315")),
    "PROCEDURE_TYPE":   int(os.getenv("FIELD_PROCEDURE_TYPE", "380307")),
    "DEALER":           int(os.getenv("FIELD_DEALER", "380335")),
    "DEADLINE":         int(os.getenv("FIELD_DEADLINE", "380317")),
    "CLOSE_REASON":     int(os.getenv("FIELD_CLOSE_REASON", "380341")),
    "ARCHIVE_DEST_FINAL": int(os.getenv("FIELD_ARCHIVE_FINAL", "380345")),
    "RETURN_DATE":      int(os.getenv("FIELD_RETURN_DATE", "380347")),
    "PRODUCTION":       int(os.getenv("FIELD_PRODUCTION", "380339")),
    "SOURCE":           int(os.getenv("FIELD_SOURCE", "380293")),
    "DEALER_DECISION":  int(os.getenv("FIELD_DEALER_DECISION", "380337")),
}

# Матрица обязательных полей
REQUIRED_FIELDS_BY_STATUS = {
    # Статус 1: LLM распознал
    "STATUS_1_LLM": [
        (FIELD_IDS["CUSTOMER"], "Заказчик", "warn"),
        (FIELD_IDS["DIRECTION"], "Направление", "warn"),
        (FIELD_IDS["PRIORITY"], "Приоритет", "warn"),
    ],
    # Статус 2: Проверка Сотрудника 2
    "STATUS_2_CHECK": [
        (FIELD_IDS["CUSTOMER"], "Заказчик", "block"),
        (FIELD_IDS["DIRECTION"], "Направление", "block"),
        (FIELD_IDS["PRIORITY"], "Приоритет", "block"),
        (FIELD_IDS["SITUATION_TYPE"], "Тип ситуации", "warn"),
    ],
    # Статус 3: СОЗ — звонок
    "STATUS_3_SOZ_CALL": [
        (FIELD_IDS["CUSTOMER"], "Заказчик", "block"),
        (FIELD_IDS["DIRECTION"], "Направление", "block"),
    ],
    # Статус 5: Передано в закупку
    "STATUS_5_PURCHASING": [
        (FIELD_IDS["CUSTOMER"], "Заказчик", "block"),
        (FIELD_IDS["DIRECTION"], "Направление", "block"),
        (FIELD_IDS["PRIORITY"], "Приоритет", "block"),
        (FIELD_IDS["NMC"], "НМЦ", "warn"),
        (FIELD_IDS["PROCEDURE_TYPE"], "Тип процедуры", "warn"),
    ],
    # Статус 6: КП готовится
    "STATUS_6_KP_PREP": [
        (FIELD_IDS["NMC"], "НМЦ", "block"),
        (FIELD_IDS["DEADLINE"], "Дедлайн подачи", "warn"),
    ],
    # Статус 7: КП передано дилеру
    "STATUS_7_KP_DEALER": [
        (FIELD_IDS["DEALER"], "Дилер", "block"),
        (FIELD_IDS["NMC"], "НМЦ", "block"),
    ],
    # Статус 8: Решение дилера
    "STATUS_8_DEALER_DEC": [
        (FIELD_IDS["DEALER"], "Дилер", "block"),
        (FIELD_IDS["DEALER_DECISION"], "Решение дилера", "warn"),
    ],
    # Статус 9: Торги
    "STATUS_9_BIDDING": [
        (FIELD_IDS["CUSTOMER"], "Заказчик", "block"),
        (FIELD_IDS["NMC"], "НМЦ", "block"),
        (FIELD_IDS["DEADLINE"], "Дата торгов", "warn"),
    ],
    # Статус 10: Производство
    "STATUS_10_PRODUCTION": [
        (FIELD_IDS["CUSTOMER"], "Заказчик", "block"),
        (FIELD_IDS["PRODUCTION"], "Производство (описание)", "warn"),
    ],
    # Статус 11: К архивированию (самый строгий)
    "STATUS_11_ARCHIVE": [
        (FIELD_IDS["CLOSE_REASON"], "Причина закрытия", "block"),
        (FIELD_IDS["ARCHIVE_DEST_FINAL"], "Архивное назначение итоговое", "block"),
        (FIELD_IDS["RETURN_DATE"], "Дата возврата из архива", "warn"),
    ],
}


# ═══════════════════════════════════════════════════════════════════
# МОДЕЛИ ДАННЫХ
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ValidationResult:
    """Результат валидации полей."""
    is_valid: bool = True
    has_blockers: bool = False      # Есть ли блокирующие ошибки
    missing_block: list = field(default_factory=list)   # Блокирующие пустые поля
    missing_warn: list = field(default_factory=list)    # Предупреждения
    message: str = ""               # Сообщение для ленты


# ═══════════════════════════════════════════════════════════════════
# ОСНОВНАЯ ЛОГИКА
# ═══════════════════════════════════════════════════════════════════

class FieldValidator:
    """Валидатор обязательных полей карточки."""

    def __init__(self):
        self.base_url = BASE_URL
        self.headers = HEADERS

    def validate_lead(self, lead_id: int, status_key: str) -> ValidationResult:
        """
        Проверить обязательные поля карточки для данного статуса.

        Args:
            lead_id: ID сделки в amoCRM
            status_key: Ключ статуса (например "STATUS_5_PURCHASING")

        Returns:
            ValidationResult
        """
        result = ValidationResult()

        # Получаем правила для статуса
        rules = REQUIRED_FIELDS_BY_STATUS.get(status_key)
        if not rules:
            logger.debug(f"Нет правил валидации для статуса {status_key}")
            return result

        # Получаем данные карточки
        lead_data = self._get_lead_fields(lead_id)
        if lead_data is None:
            result.is_valid = False
            result.message = "❌ Не удалось получить данные карточки"
            return result

        # Проверяем каждое поле
        filled_fields = lead_data.get("filled_field_ids", set())

        for field_id, field_name, severity in rules:
            if field_id not in filled_fields:
                if severity == "block":
                    result.missing_block.append(field_name)
                else:
                    result.missing_warn.append(field_name)

        # Формируем результат
        if result.missing_block:
            result.is_valid = False
            result.has_blockers = True
        elif result.missing_warn:
            result.is_valid = True  # Не блокируем, но предупреждаем

        # Формируем сообщение
        result.message = self._format_message(result, status_key)
        return result

    def validate_and_notify(self, lead_id: int, status_key: str) -> ValidationResult:
        """
        Проверить поля и написать предупреждение в ленту если есть проблемы.

        Args:
            lead_id: ID сделки
            status_key: Ключ статуса

        Returns:
            ValidationResult
        """
        result = self.validate_lead(lead_id, status_key)

        if result.missing_block or result.missing_warn:
            self._post_warning_note(lead_id, result.message)
            logger.warning(
                f"[VALIDATOR] Lead {lead_id}: "
                f"block={result.missing_block}, warn={result.missing_warn}"
            )
        else:
            logger.info(f"[VALIDATOR] Lead {lead_id}: все поля заполнены ✅")

        return result

    def check_archive_readiness(self, lead_id: int) -> ValidationResult:
        """
        Специальная проверка готовности к архивации.
        Используется ночным кроном перед переносом в архив.

        Returns:
            ValidationResult — если has_blockers=True, архивация не выполняется
        """
        return self.validate_lead(lead_id, "STATUS_11_ARCHIVE")

    def _get_lead_fields(self, lead_id: int) -> Optional[dict]:
        """Получить заполненные поля карточки из amoCRM."""
        try:
            resp = requests.get(
                f"{self.base_url}/leads/{lead_id}",
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error(f"Ошибка получения lead {lead_id}: {resp.status_code}")
                return None

            data = resp.json()
            custom_fields = data.get("custom_fields_values") or []

            # Собираем ID заполненных полей
            filled_ids = set()
            for cf in custom_fields:
                field_id = cf.get("field_id")
                values = cf.get("values", [])
                # Поле считается заполненным если есть хотя бы одно непустое значение
                for v in values:
                    val = v.get("value")
                    if val is not None and val != "" and val != 0:
                        filled_ids.add(field_id)
                        break

            return {"filled_field_ids": filled_ids, "raw": data}

        except Exception as e:
            logger.error(f"Ошибка при получении lead {lead_id}: {e}")
            return None

    def _format_message(self, result: ValidationResult, status_key: str) -> str:
        """Сформировать сообщение для ленты."""
        parts = []

        if result.missing_block:
            parts.append("🚫 БЛОКИРОВКА — не заполнены обязательные поля:")
            for field_name in result.missing_block:
                parts.append(f"  ❌ {field_name}")
            parts.append("")
            parts.append("⚠️ Карточка не будет обработана пока поля не заполнены.")

        if result.missing_warn:
            if parts:
                parts.append("")
            parts.append("⚠️ Рекомендуется заполнить:")
            for field_name in result.missing_warn:
                parts.append(f"  ⚡ {field_name}")

        if not parts:
            return "✅ Все обязательные поля заполнены"

        return "\n".join(parts)

    def _post_warning_note(self, lead_id: int, message: str):
        """Написать предупреждение в ленту карточки."""
        try:
            payload = [
                {
                    "entity_id": lead_id,
                    "note_type": "common",
                    "params": {"text": message},
                }
            ]
            resp = requests.post(
                f"{self.base_url}/leads/{lead_id}/notes",
                json=payload,
                headers=self.headers,
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"[VALIDATOR] Предупреждение записано в lead {lead_id}")
            else:
                logger.error(
                    f"[VALIDATOR] Ошибка записи заметки lead {lead_id}: "
                    f"{resp.status_code} {resp.text}"
                )
        except Exception as e:
            logger.error(f"[VALIDATOR] Ошибка при записи заметки: {e}")


# ═══════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════════

def get_status_key_by_id(status_id: int) -> Optional[str]:
    """Получить ключ статуса по его ID."""
    status_map = {
        int(os.getenv("STATUS_1_LLM", "0")): "STATUS_1_LLM",
        int(os.getenv("STATUS_2_CHECK", "0")): "STATUS_2_CHECK",
        int(os.getenv("STATUS_3_SOZ_CALL", "0")): "STATUS_3_SOZ_CALL",
        int(os.getenv("STATUS_4_SOZ_WAIT", "0")): "STATUS_4_SOZ_WAIT",
        int(os.getenv("STATUS_5_PURCHASING", "0")): "STATUS_5_PURCHASING",
        int(os.getenv("STATUS_6_KP_PREP", "0")): "STATUS_6_KP_PREP",
        int(os.getenv("STATUS_7_KP_DEALER", "0")): "STATUS_7_KP_DEALER",
        int(os.getenv("STATUS_8_DEALER_DEC", "0")): "STATUS_8_DEALER_DEC",
        int(os.getenv("STATUS_9_BIDDING", "0")): "STATUS_9_BIDDING",
        int(os.getenv("STATUS_10_PRODUCTION", "0")): "STATUS_10_PRODUCTION",
        int(os.getenv("STATUS_11_ARCHIVE", "0")): "STATUS_11_ARCHIVE",
    }
    return status_map.get(status_id)


def validate_on_status_change(lead_id: int, new_status_id: int) -> ValidationResult:
    """
    Точка входа для webhook — вызывается при смене статуса.

    Args:
        lead_id: ID сделки
        new_status_id: ID нового статуса

    Returns:
        ValidationResult
    """
    status_key = get_status_key_by_id(new_status_id)
    if not status_key:
        return ValidationResult()  # Нет правил — пропускаем

    validator = FieldValidator()
    return validator.validate_and_notify(lead_id, status_key)
