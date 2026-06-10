"""
Business rules and routing logic for RETEK amoCRM.
"""

from typing import Optional
from src.domain.enums import ActiveStatuses, ArchiveDirectionsStatuses, ArchiveSozStatuses, Pipelines, Users


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


def resolve_routing(priority: str, situation_type: str) -> tuple[int, int]:
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
    status_id = getattr(ActiveStatuses, status_name, 0)
    user_id = getattr(Users, user_name, 0)

    return status_id, user_id


# ═══════════════════════════════════════════════════════════════════
# МАТРИЦА АРХИВНОЙ МАРШРУТИЗАЦИИ
# ═══════════════════════════════════════════════════════════════════

ARCHIVE_ROUTING = {
    "Архив — направления / Специнструмент по чертежам": (
        Pipelines.ARCHIVE_DIRECTIONS,
        "SPEC_DRAWING",
    ),
    "Архив — направления / HSS ГОСТ": (
        Pipelines.ARCHIVE_DIRECTIONS,
        "HSS_GOST",
    ),
    "Архив — направления / Твердосплав": (
        Pipelines.ARCHIVE_DIRECTIONS,
        "CARBIDE",
    ),
    "Архив — направления / Алмазный": (
        Pipelines.ARCHIVE_DIRECTIONS,
        "DIAMOND",
    ),
    "Архив — направления / Не наш ассортимент": (
        Pipelines.ARCHIVE_DIRECTIONS,
        "OUT_OF_SCOPE",
    ),
    "Архив — направления / Дубли / мусор": (
        Pipelines.ARCHIVE_DIRECTIONS,
        "DUPLICATES",
    ),
    "Архив — направления / Требуется проверка": (
        Pipelines.ARCHIVE_DIRECTIONS,
        "NEEDS_CHECK",
    ),
    "Архив — СОЗ / Ждём реальные торги": (
        Pipelines.ARCHIVE_SOZ,
        "WAITING_REAL_TENDER",
    ),
    "Архив — СОЗ / К обзвону": (
        Pipelines.ARCHIVE_SOZ,
        "TO_CALL",
    ),
    "Архив — СОЗ / Повторить через 30 дней": (
        Pipelines.ARCHIVE_SOZ,
        "REPEAT_30_DAYS",
    ),
    "Архив — СОЗ / Повторить через 90 дней": (
        Pipelines.ARCHIVE_SOZ,
        "REPEAT_90_DAYS",
    ),
    "Архив — СОЗ / Интересный завод": (
        Pipelines.ARCHIVE_SOZ,
        "INTERESTING_FACTORY",
    ),
    "Архив — СОЗ / Неактуально": (
        Pipelines.ARCHIVE_SOZ,
        "IRRELEVANT",
    ),
}


def resolve_archive_destination(archive_dest_value: str) -> tuple[Optional[int], Optional[int]]:
    """
    Определить целевую воронку и статус для архивации.
    
    Returns: (pipeline_id, status_id) or (None, None) if unknown
    """
    route = ARCHIVE_ROUTING.get(archive_dest_value)
    if not route:
        return None, None

    pipeline_id, status_attr = route

    if pipeline_id == Pipelines.ARCHIVE_DIRECTIONS:
        status_id = getattr(ArchiveDirectionsStatuses, status_attr, 0)
    elif pipeline_id == Pipelines.ARCHIVE_SOZ:
        status_id = getattr(ArchiveSozStatuses, status_attr, 0)
    else:
        status_id = 0

    return pipeline_id, status_id


# ═══════════════════════════════════════════════════════════════════
# АВТОЭСКАЛАЦИЯ И КОНТРОЛЬ СРОКОВ
# ═══════════════════════════════════════════════════════════════════

ESCALATION_THRESHOLDS = {
    # status_id: max_hours_allowed
    ActiveStatuses.LLM_RECOGNIZED: 1,   # 1 час на квалификацию
    ActiveStatuses.CHECK_EMPLOYEE2: 2,  # 2 часа на разбор неясного
    ActiveStatuses.SOZ_CALL: 24,        # 1 день на звонок
    ActiveStatuses.PURCHASING: 48,      # 2 дня на закупку/просчёт
    ActiveStatuses.KP_PREPARING: 24,    # 1 день на подготовку КП
    ActiveStatuses.KP_SENT_DEALER: 72,  # 3 дня на ответ дилера
}


def auto_escalate_priority(current_priority: str, days_to_deadline: int) -> str:
    """
    Правила автоэскалации:
    - Если дедлайн просрочен (< 0) -> всегда Р1
    - Если дедлайн ≤ 2 дней -> минимум Р1
    - Если дедлайн ≤ 5 дней -> минимум Р2
    """
    if days_to_deadline < 0:
        return "Р1"
    
    if days_to_deadline <= 2:
        return "Р1"
        
    if days_to_deadline <= 5:
        if current_priority in ("Р3", "Р4", ""):
            return "Р2"
            
    return current_priority


def build_lead_name(
    priority_enum_id: int,
    customer: str,
    deadline_str: str,
    situation_type: str = "",
    product_hint: str = "",
) -> str:
    """
    Строит короткое название сделки для канбан-карточки.
    Формат: "[P1] СРОЧНО — НПО Высокоточные — 10.06"
    """
    from src.domain.enums import PRIORITY_LABELS
    
    prefix = PRIORITY_LABELS.get(priority_enum_id, "[P?]")
    customer_short = customer[:20].strip() if customer else ""
    parts = [prefix]
    if customer_short:
        parts.append(customer_short)
    if deadline_str:
        parts.append(deadline_str)
    return " — ".join(parts)
