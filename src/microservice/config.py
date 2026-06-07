"""
Конфигурация микросервиса RETEK — все правила автоматизаций.

Содержит:
- ID воронок и статусов
- ID кастомных полей
- Правила создания задач при смене статуса
- Матрица архивной маршрутизации
- Обязательные поля для архивации
- Маршрутизация новых сделок
- Таймауты и лимиты
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════════════════
# ВОРОНКИ (Pipeline IDs)
# ═══════════════════════════════════════════════════════════════════

PIPELINE_ACTIVE = 10984442          # RETEK ТЕНДЕРЫ (активная)
PIPELINE_ARCHIVE_DIRECTIONS = 10984454  # Архив — Направления
PIPELINE_ARCHIVE_SOZ = 10985038     # Архив — СОЗ / развитие

# ═══════════════════════════════════════════════════════════════════
# СТАТУСЫ АКТИВНОЙ ВОРОНКИ
# ═══════════════════════════════════════════════════════════════════
# Заполняется из amoCRM API при первом запуске (или вручную)
# Формат: STATUS_<НОМЕР>_<КРАТКОЕ_ИМЯ> = status_id

class ActiveStatuses:
    """Статусы воронки 'RETEK ТЕНДЕРЫ'."""
    LLM_RECOGNIZED = int(os.getenv("STATUS_1_LLM", "0"))
    CHECK_EMPLOYEE2 = int(os.getenv("STATUS_2_CHECK", "0"))
    SOZ_CALL = int(os.getenv("STATUS_3_SOZ_CALL", "0"))
    SOZ_WAIT = int(os.getenv("STATUS_4_SOZ_WAIT", "0"))
    PURCHASING = int(os.getenv("STATUS_5_PURCHASING", "0"))
    KP_PREPARING = int(os.getenv("STATUS_6_KP_PREP", "0"))
    KP_SENT_DEALER = int(os.getenv("STATUS_7_KP_DEALER", "0"))
    DEALER_DECISION = int(os.getenv("STATUS_8_DEALER_DEC", "0"))
    PRODUCTION = int(os.getenv("STATUS_9_PRODUCTION", "0"))
    TO_ARCHIVE = int(os.getenv("STATUS_10_ARCHIVE", "0"))


# ═══════════════════════════════════════════════════════════════════
# СТАТУСЫ АРХИВНЫХ ВОРОНОК
# ═══════════════════════════════════════════════════════════════════

class ArchiveDirectionsStatuses:
    """Статусы воронки 'Архив — Направления'."""
    SPEC_DRAWING = int(os.getenv("ARCH_DIR_SPEC", "0"))
    HSS_GOST = int(os.getenv("ARCH_DIR_HSS", "0"))
    CARBIDE = int(os.getenv("ARCH_DIR_CARBIDE", "0"))
    DIAMOND = int(os.getenv("ARCH_DIR_DIAMOND", "0"))
    OUT_OF_SCOPE = int(os.getenv("ARCH_DIR_OUT", "0"))
    DUPLICATES = int(os.getenv("ARCH_DIR_DUPL", "0"))
    NEEDS_CHECK = int(os.getenv("ARCH_DIR_CHECK", "0"))


class ArchiveSozStatuses:
    """Статусы воронки 'Архив — СОЗ / развитие'."""
    WAITING_REAL_TENDER = int(os.getenv("ARCH_SOZ_WAIT", "0"))
    TO_CALL = int(os.getenv("ARCH_SOZ_CALL", "0"))
    REPEAT_30_DAYS = int(os.getenv("ARCH_SOZ_30D", "0"))
    REPEAT_90_DAYS = int(os.getenv("ARCH_SOZ_90D", "0"))
    INTERESTING_FACTORY = int(os.getenv("ARCH_SOZ_FACTORY", "0"))
    IRRELEVANT = int(os.getenv("ARCH_SOZ_IRRELEVANT", "0"))


# ═══════════════════════════════════════════════════════════════════
# КАСТОМНЫЕ ПОЛЯ (Field IDs)
# ═══════════════════════════════════════════════════════════════════
# IDs 380291–380353 (созданы скриптом create_custom_fields.py)

class Fields:
    """ID кастомных полей сделки."""
    EXTERNAL_ID = int(os.getenv("FIELD_EXTERNAL_ID", "380291"))
    SOURCE = int(os.getenv("FIELD_SOURCE", "380293"))
    PLATFORM_URL = int(os.getenv("FIELD_PLATFORM_URL", "380295"))
    DOCS_URL = int(os.getenv("FIELD_DOCS_URL", "380297"))
    CUSTOMER = int(os.getenv("FIELD_CUSTOMER", "380299"))
    INN = int(os.getenv("FIELD_INN", "380301"))
    PROCEDURE_NUMBER = int(os.getenv("FIELD_PROCEDURE_NUM", "380303"))
    SITUATION_TYPE = int(os.getenv("FIELD_SITUATION_TYPE", "380305"))
    PROCEDURE_TYPE = int(os.getenv("FIELD_PROCEDURE_TYPE", "380307"))
    PRIORITY = int(os.getenv("FIELD_PRIORITY", "380309"))
    DIRECTION = int(os.getenv("FIELD_DIRECTION", "380311"))
    SUB_DIRECTION = int(os.getenv("FIELD_SUB_DIRECTION", "380313"))
    NMC = int(os.getenv("FIELD_NMC", "380315"))
    DEADLINE = int(os.getenv("FIELD_DEADLINE", "380317"))
    NEXT_ACTION = int(os.getenv("FIELD_NEXT_ACTION", "380319"))
    NEXT_ACTION_DATE = int(os.getenv("FIELD_NEXT_ACTION_DATE", "380321"))
    RESPONSIBLE_SALES = int(os.getenv("FIELD_RESP_SALES", "380323"))
    RESPONSIBLE_BUYER = int(os.getenv("FIELD_RESP_BUYER", "380325"))
    TEAM = int(os.getenv("FIELD_TEAM", "380327"))
    NEEDS_PURCHASING = int(os.getenv("FIELD_NEEDS_PURCH", "380329"))
    SOZ_DOUBTS = int(os.getenv("FIELD_SOZ_DOUBTS", "380331"))
    # KP_STATUS (380333) — удалено: дублировало статус воронки
    DEALER = int(os.getenv("FIELD_DEALER", "380335"))
    DEALER_DECISION = int(os.getenv("FIELD_DEALER_DEC", "380337"))
    PRODUCTION = int(os.getenv("FIELD_PRODUCTION", "380339"))
    CLOSE_REASON = int(os.getenv("FIELD_CLOSE_REASON", "380341"))
    ARCHIVE_DEST_LLM = int(os.getenv("FIELD_ARCH_DEST_LLM", "380343"))
    ARCHIVE_DEST_FINAL = int(os.getenv("FIELD_ARCH_DEST_FINAL", "380345"))
    RETURN_DATE = int(os.getenv("FIELD_RETURN_DATE", "380347"))
    LLM_CONFIDENCE = int(os.getenv("FIELD_LLM_CONFIDENCE", "380349"))
    LLM_COMMENT = int(os.getenv("FIELD_LLM_COMMENT", "380351"))
    MANAGER_COMMENT = int(os.getenv("FIELD_MANAGER_COMMENT", "380353"))


# ═══════════════════════════════════════════════════════════════════
# ПОЛЬЗОВАТЕЛИ (User IDs)
# ═══════════════════════════════════════════════════════════════════

class Users:
    """ID пользователей amoCRM."""
    EMPLOYEE_2_SALES = int(os.getenv("USER_EMPLOYEE_2", "0"))  # Продажник/квалификатор
    EMPLOYEE_3_BUYER = int(os.getenv("USER_EMPLOYEE_3", "0"))  # Закупщик/расчётчик
    MANAGER = int(os.getenv("USER_MANAGER", "0"))              # Руководитель


# ═══════════════════════════════════════════════════════════════════
# ПРАВИЛА АВТОЗАДАЧ ПРИ СМЕНЕ СТАТУСА
# ═══════════════════════════════════════════════════════════════════
# Формат: status_id → {text, responsible, deadline_seconds, task_type_id}
# task_type_id: 1=Звонок, 2=Встреча, 3=Написать письмо

STATUS_TASK_RULES = {
    # → 1. LLM распознал: задача Сотруднику 2 «Проверить классификацию LLM» (2ч)
    "LLM_RECOGNIZED": {
        "text": "Проверить классификацию LLM — подтвердить или исправить направление, приоритет, тип ситуации",
        "responsible": "EMPLOYEE_2_SALES",
        "deadline_seconds": 2 * 3600,  # 2 часа
        "task_type_id": 1,
    },
    # → 3. СОЗ — звонок: задача Сотруднику 2 «Позвонить, уточнить дату торгов» (1 день)
    "SOZ_CALL": {
        "text": "Позвонить заказчику, уточнить дату реальных торгов и предмет закупки",
        "responsible": "EMPLOYEE_2_SALES",
        "deadline_seconds": 24 * 3600,  # 1 день
        "task_type_id": 1,
    },
    # → 5. Передано в закупку: задача Сотруднику 3 «Рассчитать себестоимость и КП» (2 дня)
    "PURCHASING": {
        "text": "Рассчитать себестоимость, подготовить КП. Проверить наличие у поставщиков",
        "responsible": "EMPLOYEE_3_BUYER",
        "deadline_seconds": 2 * 24 * 3600,  # 2 дня
        "task_type_id": 3,
    },
    # → 7. КП передано дилеру: задача Сотруднику 2 «Получить решение дилера» (3 дня)
    "KP_SENT_DEALER": {
        "text": "Получить решение дилера: выходим на торги или нет. Зафиксировать в карточке",
        "responsible": "EMPLOYEE_2_SALES",
        "deadline_seconds": 3 * 24 * 3600,  # 3 дня
        "task_type_id": 1,
    },
    # → 10. К архивированию: задача ответственному «Заполнить причину и назначение» (4ч)
    "TO_ARCHIVE": {
        "text": "Заполнить причину закрытия и архивное назначение. Указать дату возврата если нужно",
        "responsible": "_LEAD_RESPONSIBLE",  # Специальное значение: ответственный за сделку
        "deadline_seconds": 4 * 3600,  # 4 часа
        "task_type_id": 3,
    },
}

# Маппинг имён статусов → status_id (заполняется из ActiveStatuses)
def get_status_task_rules() -> dict:
    """Получить правила с реальными status_id."""
    mapping = {
        "LLM_RECOGNIZED": ActiveStatuses.LLM_RECOGNIZED,
        "SOZ_CALL": ActiveStatuses.SOZ_CALL,
        "PURCHASING": ActiveStatuses.PURCHASING,
        "KP_SENT_DEALER": ActiveStatuses.KP_SENT_DEALER,
        "TO_ARCHIVE": ActiveStatuses.TO_ARCHIVE,
    }
    result = {}
    for key, status_id in mapping.items():
        if status_id:
            rule = STATUS_TASK_RULES[key].copy()
            # Resolve responsible
            if rule["responsible"] == "EMPLOYEE_2_SALES":
                rule["responsible_user_id"] = Users.EMPLOYEE_2_SALES
            elif rule["responsible"] == "EMPLOYEE_3_BUYER":
                rule["responsible_user_id"] = Users.EMPLOYEE_3_BUYER
            elif rule["responsible"] == "_LEAD_RESPONSIBLE":
                rule["responsible_user_id"] = None  # Определяется из сделки
            result[status_id] = rule
    return result


# ═══════════════════════════════════════════════════════════════════
# МАРШРУТИЗАЦИЯ НОВЫХ СДЕЛОК (из LLM)
# ═══════════════════════════════════════════════════════════════════
# Приоритет + Тип ситуации → (статус, ответственный)

ROUTING_RULES = {
    # Р1/Р2/Р3 + СОЗ → Сотрудник 2, статус «СОЗ — звонок»
    ("Р1", "СОЗ"): ("SOZ_CALL", "EMPLOYEE_2_SALES"),
    ("Р2", "СОЗ"): ("SOZ_CALL", "EMPLOYEE_2_SALES"),
    ("Р3", "СОЗ"): ("SOZ_CALL", "EMPLOYEE_2_SALES"),
    # Р1/Р2/Р3 + Реальные торги → Сотрудник 3, статус «Передано в закупку»
    ("Р1", "Запрос котировок / реальные торги"): ("PURCHASING", "EMPLOYEE_3_BUYER"),
    ("Р2", "Запрос котировок / реальные торги"): ("PURCHASING", "EMPLOYEE_3_BUYER"),
    ("Р3", "Запрос котировок / реальные торги"): ("PURCHASING", "EMPLOYEE_3_BUYER"),
    # Неясно → Сотрудник 2, статус «Проверка Сотрудника 2»
    ("Р1", "Неясно"): ("CHECK_EMPLOYEE2", "EMPLOYEE_2_SALES"),
    ("Р2", "Неясно"): ("CHECK_EMPLOYEE2", "EMPLOYEE_2_SALES"),
    ("Р3", "Неясно"): ("CHECK_EMPLOYEE2", "EMPLOYEE_2_SALES"),
    # Р4 → К архивированию (любой тип ситуации)
    ("Р4", "СОЗ"): ("TO_ARCHIVE", "EMPLOYEE_2_SALES"),
    ("Р4", "Запрос котировок / реальные торги"): ("TO_ARCHIVE", "EMPLOYEE_2_SALES"),
    ("Р4", "Неясно"): ("TO_ARCHIVE", "EMPLOYEE_2_SALES"),
    ("Р4", "Не наш ассортимент"): ("TO_ARCHIVE", "EMPLOYEE_2_SALES"),
    # Не наш ассортимент (любой приоритет) → К архивированию
    ("Р1", "Не наш ассортимент"): ("TO_ARCHIVE", "EMPLOYEE_2_SALES"),
    ("Р2", "Не наш ассортимент"): ("TO_ARCHIVE", "EMPLOYEE_2_SALES"),
    ("Р3", "Не наш ассортимент"): ("TO_ARCHIVE", "EMPLOYEE_2_SALES"),
}


def resolve_routing(priority: str, situation_type: str) -> tuple:
    """
    Определить статус и ответственного для новой сделки.
    
    Returns: (status_id, responsible_user_id)
    """
    key = (priority, situation_type)
    rule = ROUTING_RULES.get(key)

    if not rule:
        # Fallback: Проверка Сотрудника 2
        return ActiveStatuses.CHECK_EMPLOYEE2, Users.EMPLOYEE_2_SALES

    status_name, user_name = rule

    # Resolve status
    status_id = getattr(ActiveStatuses, status_name, 0)

    # Resolve user
    user_id = getattr(Users, user_name, 0)

    return status_id, user_id


# ═══════════════════════════════════════════════════════════════════
# МАТРИЦА АРХИВНОЙ МАРШРУТИЗАЦИИ
# ═══════════════════════════════════════════════════════════════════
# Значение поля «Архивное назначение итоговое» → (pipeline_id, status_id)

ARCHIVE_ROUTING = {
    "Архив — направления / Специнструмент по чертежам": (
        PIPELINE_ARCHIVE_DIRECTIONS,
        "SPEC_DRAWING",
    ),
    "Архив — направления / HSS ГОСТ": (
        PIPELINE_ARCHIVE_DIRECTIONS,
        "HSS_GOST",
    ),
    "Архив — направления / Твердосплав": (
        PIPELINE_ARCHIVE_DIRECTIONS,
        "CARBIDE",
    ),
    "Архив — направления / Алмазный": (
        PIPELINE_ARCHIVE_DIRECTIONS,
        "DIAMOND",
    ),
    "Архив — направления / Не наш ассортимент": (
        PIPELINE_ARCHIVE_DIRECTIONS,
        "OUT_OF_SCOPE",
    ),
    "Архив — направления / Дубли / мусор": (
        PIPELINE_ARCHIVE_DIRECTIONS,
        "DUPLICATES",
    ),
    "Архив — направления / Требуется проверка": (
        PIPELINE_ARCHIVE_DIRECTIONS,
        "NEEDS_CHECK",
    ),
    "Архив — СОЗ / Ждём реальные торги": (
        PIPELINE_ARCHIVE_SOZ,
        "WAITING_REAL_TENDER",
    ),
    "Архив — СОЗ / К обзвону": (
        PIPELINE_ARCHIVE_SOZ,
        "TO_CALL",
    ),
    "Архив — СОЗ / Повторить через 30 дней": (
        PIPELINE_ARCHIVE_SOZ,
        "REPEAT_30_DAYS",
    ),
    "Архив — СОЗ / Повторить через 90 дней": (
        PIPELINE_ARCHIVE_SOZ,
        "REPEAT_90_DAYS",
    ),
    "Архив — СОЗ / Интересный завод": (
        PIPELINE_ARCHIVE_SOZ,
        "INTERESTING_FACTORY",
    ),
    "Архив — СОЗ / Неактуально": (
        PIPELINE_ARCHIVE_SOZ,
        "IRRELEVANT",
    ),
}


def resolve_archive_destination(archive_dest_value: str) -> tuple:
    """
    Определить целевую воронку и статус для архивации.
    
    Returns: (pipeline_id, status_id) or (None, None) if unknown
    """
    route = ARCHIVE_ROUTING.get(archive_dest_value)
    if not route:
        return None, None

    pipeline_id, status_attr = route

    # Resolve status_id from class
    if pipeline_id == PIPELINE_ARCHIVE_DIRECTIONS:
        status_id = getattr(ArchiveDirectionsStatuses, status_attr, 0)
    elif pipeline_id == PIPELINE_ARCHIVE_SOZ:
        status_id = getattr(ArchiveSozStatuses, status_attr, 0)
    else:
        status_id = 0

    return pipeline_id, status_id


# ═══════════════════════════════════════════════════════════════════
# ОБЯЗАТЕЛЬНЫЕ ПОЛЯ ДЛЯ АРХИВАЦИИ
# ═══════════════════════════════════════════════════════════════════

ARCHIVE_REQUIRED_FIELDS = [
    Fields.SITUATION_TYPE,       # Тип ситуации
    Fields.PRIORITY,             # Приоритет
    Fields.DIRECTION,            # Направление
    Fields.SUB_DIRECTION,        # Подтип направления
    Fields.CLOSE_REASON,         # Причина закрытия
    Fields.ARCHIVE_DEST_LLM,    # Архивное назначение LLM
    Fields.ARCHIVE_DEST_FINAL,  # Архивное назначение итоговое
    Fields.RETURN_DATE,          # Дата возврата из архива
    Fields.NEXT_ACTION,          # Следующее действие
]

ARCHIVE_REQUIRED_FIELD_NAMES = {
    Fields.SITUATION_TYPE: "Тип ситуации",
    Fields.PRIORITY: "Приоритет",
    Fields.DIRECTION: "Направление",
    Fields.SUB_DIRECTION: "Подтип направления",
    Fields.CLOSE_REASON: "Причина закрытия",
    Fields.ARCHIVE_DEST_LLM: "Архивное назначение LLM",
    Fields.ARCHIVE_DEST_FINAL: "Архивное назначение итоговое",
    Fields.RETURN_DATE: "Дата возврата из архива",
    Fields.NEXT_ACTION: "Следующее действие",
}


# ═══════════════════════════════════════════════════════════════════
# ТАЙМАУТЫ И ЛИМИТЫ
# ═══════════════════════════════════════════════════════════════════

# Зависшая карточка: > N дней в одном статусе
STUCK_LEAD_DAYS = 7

# WIP-лимиты (максимум сделок в работе у одного сотрудника)
WIP_LIMIT_EMPLOYEE_2 = 20
WIP_LIMIT_EMPLOYEE_3 = 15

# Приоритеты для контроля (только Р1 и Р2 контролируются каждый час)
PRIORITY_CONTROL = ["Р1", "Р2"]

# Максимальное время без задачи для Р1/Р2 (в секундах)
MAX_NO_TASK_P1 = 2 * 3600   # 2 часа
MAX_NO_TASK_P2 = 4 * 3600   # 4 часа
