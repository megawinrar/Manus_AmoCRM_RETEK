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
# Воронка: RETEK ТЕНДЕРЫ (pipeline 10984442)
# sort=20  id=86357690  "1. LLM распознал"
# sort=30  id=86357686  "2. Проверка Сотрудника 2"
# sort=40  id=86357682  "3. СОЗ — звонок / уточнить дату"
# sort=50  id=86357678  "4. СОЗ — ждём реальный торг"
# sort=60  id=86357674  "5. Передано в закупку / расчёт"
# sort=70  id=86357670  "6. КП готовится"
# sort=80  id=86357666  "7. КП передано дилеру"
# sort=90  id=86357662  "8. Решение дилера"
# sort=100 id=86357658  "9. Торги"
# sort=110 id=86357918  "10. Производство"
# sort=120 id=86357654  "11. К архивированию"

class ActiveStatuses:
    """Статусы воронки 'RETEK ТЕНДЕРЫ'."""
    LLM_RECOGNIZED  = int(os.getenv("STATUS_1_LLM",        "0"))  # 1. LLM распознал
    CHECK_EMPLOYEE2 = int(os.getenv("STATUS_2_CHECK",       "0"))  # 2. Проверка Сотрудника 2
    SOZ_CALL        = int(os.getenv("STATUS_3_SOZ_CALL",    "0"))  # 3. СОЗ — звонок
    SOZ_WAIT        = int(os.getenv("STATUS_4_SOZ_WAIT",    "0"))  # 4. СОЗ — ждём дату
    PURCHASING      = int(os.getenv("STATUS_5_PURCHASING",  "0"))  # 5. Передано в закупку
    KP_PREPARING    = int(os.getenv("STATUS_6_KP_PREP",     "0"))  # 6. КП готовится
    KP_SENT_DEALER  = int(os.getenv("STATUS_7_KP_DEALER",   "0"))  # 7. КП передано дилеру
    DEALER_DECISION = int(os.getenv("STATUS_8_DEALER_DEC",  "0"))  # 8. Решение дилера
    BIDDING         = int(os.getenv("STATUS_9_BIDDING",     "0"))  # 9. Торги
    PRODUCTION      = int(os.getenv("STATUS_10_PRODUCTION", "0"))  # 10. Производство
    TO_ARCHIVE      = int(os.getenv("STATUS_11_ARCHIVE",    "0"))  # 11. К архивированию


# ═══════════════════════════════════════════════════════════════════
# СТАТУСЫ АРХИВНЫХ ВОРОНОК
# ═══════════════════════════════════════════════════════════════════

class ArchiveDirectionsStatuses:
    """Статусы воронки 'Архив — Направления'."""
    SPEC_DRAWING = int(os.getenv("ARCH_DIR_SPEC",    "0"))
    HSS_GOST     = int(os.getenv("ARCH_DIR_HSS",     "0"))
    CARBIDE      = int(os.getenv("ARCH_DIR_CARBIDE", "0"))
    DIAMOND      = int(os.getenv("ARCH_DIR_DIAMOND", "0"))
    OUT_OF_SCOPE = int(os.getenv("ARCH_DIR_OUT",     "0"))
    DUPLICATES   = int(os.getenv("ARCH_DIR_DUPL",    "0"))
    NEEDS_CHECK  = int(os.getenv("ARCH_DIR_CHECK",   "0"))


class ArchiveSozStatuses:
    """Статусы воронки 'Архив — СОЗ / развитие'."""
    WAITING_REAL_TENDER  = int(os.getenv("ARCH_SOZ_WAIT",       "0"))
    TO_CALL              = int(os.getenv("ARCH_SOZ_CALL",       "0"))
    REPEAT_30_DAYS       = int(os.getenv("ARCH_SOZ_30D",        "0"))
    REPEAT_90_DAYS       = int(os.getenv("ARCH_SOZ_90D",        "0"))
    INTERESTING_FACTORY  = int(os.getenv("ARCH_SOZ_FACTORY",    "0"))
    IRRELEVANT           = int(os.getenv("ARCH_SOZ_IRRELEVANT", "0"))


# ═══════════════════════════════════════════════════════════════════
# КАСТОМНЫЕ ПОЛЯ (Field IDs)
# ═══════════════════════════════════════════════════════════════════
# IDs 380291–380353 (созданы скриптом create_custom_fields.py)

class Fields:
    """ID кастомных полей сделки."""
    EXTERNAL_ID      = int(os.getenv("FIELD_EXTERNAL_ID",    "380291"))
    SOURCE           = int(os.getenv("FIELD_SOURCE",          "380293"))
    PLATFORM_URL     = int(os.getenv("FIELD_PLATFORM_URL",    "380295"))
    DOCS_URL         = int(os.getenv("FIELD_DOCS_URL",        "380297"))
    CUSTOMER         = int(os.getenv("FIELD_CUSTOMER",        "380299"))
    INN              = int(os.getenv("FIELD_INN",             "380301"))
    PROCEDURE_NUMBER = int(os.getenv("FIELD_PROCEDURE_NUM",   "380303"))
    SITUATION_TYPE   = int(os.getenv("FIELD_SITUATION_TYPE",  "380305"))
    PROCEDURE_TYPE   = int(os.getenv("FIELD_PROCEDURE_TYPE",  "380307"))
    PRIORITY         = int(os.getenv("FIELD_PRIORITY",        "380309"))
    DIRECTION        = int(os.getenv("FIELD_DIRECTION",       "380311"))
    SUB_DIRECTION    = int(os.getenv("FIELD_DIRECTION_SUBTYPE","380313"))
    NMC              = int(os.getenv("FIELD_NMC",             "380315"))
    DEADLINE         = int(os.getenv("FIELD_DEADLINE",        "380317"))
    NEXT_ACTION      = int(os.getenv("FIELD_NEXT_ACTION",     "380319"))
    NEXT_ACTION_DATE = int(os.getenv("FIELD_NEXT_ACTION_DATE","380321"))
    RESPONSIBLE_SALES  = int(os.getenv("FIELD_RESP_SALES",    "380323"))
    RESPONSIBLE_BUYER  = int(os.getenv("FIELD_RESP_PURCHASE", "380325"))
    TEAM             = int(os.getenv("FIELD_TEAM",            "380327"))
    NEEDS_PURCHASING = int(os.getenv("FIELD_NEEDS_PURCHASE",  "380329"))
    SOZ_DOUBTS       = int(os.getenv("FIELD_SOZ_DOUBT",       "380331"))
    # FIELD_KP_STATUS (380333) — удалено: дублировало статус воронки
    DEALER           = int(os.getenv("FIELD_DEALER",          "380335"))
    DEALER_DECISION  = int(os.getenv("FIELD_DEALER_DECISION", "380337"))
    PRODUCTION       = int(os.getenv("FIELD_PRODUCTION",      "380339"))
    CLOSE_REASON     = int(os.getenv("FIELD_CLOSE_REASON",    "380341"))
    ARCHIVE_DEST_LLM   = int(os.getenv("FIELD_ARCHIVE_LLM",  "380343"))
    ARCHIVE_DEST_FINAL = int(os.getenv("FIELD_ARCHIVE_FINAL", "380345"))
    RETURN_DATE      = int(os.getenv("FIELD_RETURN_DATE",     "380347"))
    LLM_CONFIDENCE   = int(os.getenv("FIELD_LLM_CONFIDENCE",  "380349"))
    LLM_COMMENT      = int(os.getenv("FIELD_LLM_COMMENT",     "380351"))
    MANAGER_COMMENT  = int(os.getenv("FIELD_MANAGER_COMMENT", "380353"))


# ═══════════════════════════════════════════════════════════════════
# ПОЛЬЗОВАТЕЛИ (User IDs)
# ═══════════════════════════════════════════════════════════════════

class Users:
    """ID пользователей amoCRM."""
    EMPLOYEE_2_SALES = int(os.getenv("USER_EMPLOYEE_2", "0"))  # Продажник/квалификатор
    EMPLOYEE_3_BUYER = int(os.getenv("USER_EMPLOYEE_3", "0"))  # Закупщик/расчётчик
    MANAGER          = int(os.getenv("USER_MANAGER",    "0"))  # Руководитель


# ═══════════════════════════════════════════════════════════════════
# ПРАВИЛА АВТОЗАДАЧ ПРИ СМЕНЕ СТАТУСА
# ═══════════════════════════════════════════════════════════════════
# Формат: status_key → {text, responsible, deadline_seconds, task_type_id}
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
    # → 9. Торги: задача ответственному «Контролировать ход торгов» (1 день)
    "BIDDING": {
        "text": "Контролировать ход торгов. После результата — зафиксировать итог и перевести в «Производство» или «К архивированию»",
        "responsible": "_LEAD_RESPONSIBLE",  # Ответственный за сделку
        "deadline_seconds": 24 * 3600,  # 1 день
        "task_type_id": 1,
    },
    # → 11. К архивированию: задача ответственному «Заполнить причину и назначение» (4ч)
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
        "SOZ_CALL":        ActiveStatuses.SOZ_CALL,
        "PURCHASING":      ActiveStatuses.PURCHASING,
        "KP_SENT_DEALER":  ActiveStatuses.KP_SENT_DEALER,
        "BIDDING":         ActiveStatuses.BIDDING,
        "TO_ARCHIVE":      ActiveStatuses.TO_ARCHIVE,
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
    Fields.ARCHIVE_DEST_LLM,     # Архивное назначение LLM
    Fields.ARCHIVE_DEST_FINAL,   # Архивное назначение итоговое
    Fields.RETURN_DATE,          # Дата возврата из архива
    Fields.NEXT_ACTION,          # Следующее действие
]

ARCHIVE_REQUIRED_FIELD_NAMES = {
    Fields.SITUATION_TYPE:     "Тип ситуации",
    Fields.PRIORITY:           "Приоритет",
    Fields.DIRECTION:          "Направление",
    Fields.SUB_DIRECTION:      "Подтип направления",
    Fields.CLOSE_REASON:       "Причина закрытия",
    Fields.ARCHIVE_DEST_LLM:   "Архивное назначение LLM",
    Fields.ARCHIVE_DEST_FINAL: "Архивное назначение итоговое",
    Fields.RETURN_DATE:        "Дата возврата из архива",
    Fields.NEXT_ACTION:        "Следующее действие",
}


# ═══════════════════════════════════════════════════════════════════
# ШАБЛОНЫ СООБЩЕНИЙ В ЛЕНТУ КАРТОЧКИ
# ═══════════════════════════════════════════════════════════════════
# Пишутся автоматически в ленту карточки при каждой смене статуса.
# Цель: пояснять что произошло и что делать дальше.
# Первые 44 символа видны в превью канбан-карточки.

STATUS_NOTE_TEMPLATES = {
    # 1. LLM распознал
    # Канбан-превью (44 симв): "🤖 Авто-создано. Проверь классификацию"
    "LLM_RECOGNIZED": (
        "🤖 Авто-создано. Проверь классификацию.\n"
        "─────────────────────────────────────\n"
        "✔️ Заполнено: направление, приоритет, тип ситуации, заказчик.\n"
        "📌 Проверь: правильно ли определены направление и приоритет.\n"
        "➡️ Если верно → «Проверка Сотрудника 2» (нужна квалификация)\n"
        "   или сразу → «Передано в закупку» (тендер понятен)"
    ),
    # 2. Проверка Сотрудника 2
    # Канбан-превью (44 симв): "🔍 На квалификации. Уточни направление"
    "CHECK_EMPLOYEE2": (
        "🔍 На квалификации. Уточни направление.\n"
        "─────────────────────────────────────\n"
        "📌 Разберись в тендере, уточни направление и приоритет.\n"
        "➡️ Наш ассортимент → «Передано в закупку» или «СОЗ — звонок»\n"
        "   Не наш → «К архивированию» (заполни причину закрытия)"
    ),
    # 3. СОЗ — звонок
    # Канбан-превью (44 симв): "📞 СОЗ: позвони, узнай дату реальных торг"
    "SOZ_CALL": (
        "📞 СОЗ: позвони, узнай дату реальных торгов.\n"
        "─────────────────────────────────────────\n"
        "📌 Позвонить заказчику: когда объявят реальные торги, что закупают.\n"
        "➡️ Торги скоро → «СОЗ — ждём дату»\n"
        "   Торги уже идут → «Передано в закупку» (заполни срок подачи)"
    ),
    # 4. СОЗ — ждём дату
    # Канбан-превью (44 симв): "⏳ СОЗ: ждём объявления торгов. Следи за"
    "SOZ_WAIT": (
        "⏳ СОЗ: ждём объявления торгов. Следи за площадкой.\n"
        "──────────────────────────────────────────────────\n"
        "📌 Звонок сделан, дата зафиксирована. Мониторить площадку.\n"
        "➡️ Торги объявлены → «Передано в закупку» (заполни дату подачи)"
    ),
    # 5. Передано в закупку
    # Канбан-превью (44 симв): "📦 В закупке. Считай КП к дате подачи"
    "PURCHASING": (
        "📦 В закупке. Считай КП к дате подачи.\n"
        "──────────────────────────────────────\n"
        "📌 Рассчитать себестоимость, проверить наличие у поставщиков.\n"
        "   Срок → поле «Срок подачи».\n"
        "➡️ КП готово → «КП готовится» (согласование) или «КП передано дилеру»"
    ),
    # 6. КП готовится
    # Канбан-превью (44 симв): "📝 КП готово. Проверь цены и отправь"
    "KP_PREPARING": (
        "📝 КП готово. Проверь цены и отправь дилеру.\n"
        "───────────────────────────────────────────\n"
        "📌 Убедись: цены актуальны, все позиции включены, документы готовы.\n"
        "➡️ Отправь → «КП передано дилеру» (заполни поле «Дилер / канал продаж»)"
    ),
    # 7. КП передано дилеру
    # Канбан-превью (44 симв): "📤 КП у дилера. Жди решения о торгах"
    "KP_SENT_DEALER": (
        "📤 КП у дилера. Жди решения о торгах.\n"
        "──────────────────────────────────────\n"
        "📌 Дождаться ответа дилера: выходит на торги или нет.\n"
        "➡️ Ответил → заполни «Решение дилера» и переведи:\n"
        "   Выходим → «Решение дилера»\n"
        "   Не выходим → «К архивированию» (заполни причину)"
    ),
    # 8. Решение дилера
    # Канбан-превью (44 симв): "🤝 Реш. дилера. Заполни поле и двигай"
    "DEALER_DECISION": (
        "🤝 Реш. дилера. Заполни поле и двигай дальше.\n"
        "──────────────────────────────────────────────\n"
        "📌 Заполни поле «Решение дилера»:\n"
        "   Выходим на торги / Не выходим / Не ответил / Торги отменены\n"
        "➡️ Выходим → «9. Торги»\n"
        "   Не выходим → «К архивированию» (заполни причину закрытия)"
    ),
    # 9. Торги
    # Канбан-превью (44 симв): "⚔️ Торги идут! Следи за ходом и итогом"
    "BIDDING": (
        "⚔️ Торги идут! Следи за ходом и итогом.\n"
        "─────────────────────────────────────────\n"
        "📌 Контролировать ход торгов, фиксировать результат в реальном времени.\n\n"
        "➡️ После торгов — переведи в «11. К архивированию» и заполни:\n\n"
        "  «Причина закрытия»:\n"
        "    Выиграли           — тендер выигран, идёт в производство\n"
        "    Проиграли          — участвовали, но не выиграли\n"
        "    Не участвовали     — решили не выходить на торги\n"
        "    Торги отменены     — площадка отменила процедуру\n\n"
        "  «Архивное назначение итоговое» — куда уйдёт карточка:\n"
        "    Специнструмент по чертежам   → Архив — направления / Специнструмент по чертежам\n"
        "    HSS / ГОСТ                   → Архив — направления / HSS ГОСТ\n"
        "    Твердосплав                  → Архив — направления / Твердосплав\n"
        "    Алмазный                     → Архив — направления / Алмазный\n"
        "    СОЗ (ждём реальные торги)    → Архив — СОЗ / Ждём реальные торги\n"
        "    Не наш ассортимент           → Архив — направления / Не наш ассортимент\n\n"
        "  «Дата возврата из архива» (если нужно вернуться):\n"
        "    Выиграли — проверить контракт      → +180 дней\n"
        "    Проиграли, заказчик интересный     → +180 дней\n"
        "    Торги отменены (перенесут)          → +45 дней\n"
        "    Без даты — карточка остаётся в архиве навсегда\n\n"
        "⏰ Микросервис перенесёт ночью (если все поля заполнены)."
    ),
    # 10. Производство
    # Канбан-превью (44 симв): "🏭 В производстве. Контроль сроков и отгр"
    "PRODUCTION": (
        "🏭 В производстве. Контроль сроков и отгрузки.\n"
        "───────────────────────────────────────────────\n"
        "📌 Тендер выигран, передан в производство. Контролировать сроки изготовления и отгрузки.\n\n"
        "➡️ После отгрузки — переведи в «11. К архивированию» и заполни:\n\n"
        "  «Причина закрытия»:\n"
        "    Выиграли           — тендер выигран и исполнен\n"
        "    Торги отменены     — если контракт расторгнут или отменён\n\n"
        "  «Архивное назначение итоговое» — куда уйдёт карточка:\n"
        "    Специнструмент по чертежам   → Архив — направления / Специнструмент по чертежам\n"
        "    HSS / ГОСТ                   → Архив — направления / HSS ГОСТ\n"
        "    Твердосплав                  → Архив — направления / Твердосплав\n"
        "    Алмазный                     → Архив — направления / Алмазный\n\n"
        "  «Дата возврата из архива»:\n"
        "    Выиграли — проверить повторный заказ   → +180 дней\n"
        "    Без даты — карточка остаётся в архиве навсегда\n\n"
        "⏰ Микросервис перенесёт ночью (если все поля заполнены)."
    ),
    # 11. К архивированию
    # Канбан-превью (44 симв): "🗂️ К архиву. Заполни причину и назначен"
    "TO_ARCHIVE": (
        "🗂️ К архиву. Заполни причину и назначение.\n"
        "──────────────────────────────────────────\n"
        "📌 Обязательные поля:\n"
        "  «Причина закрытия»: Выиграли / Проиграли / Не участвовали / Торги отменены / Дубль / Не наш\n"
        "  «Архивное назначение итоговое»: выбери воронку архива\n"
        "  «Дата возврата из архива»: если нужно вернуться (без даты — в архиве навсегда)\n\n"
        "📅 Подсказка по дате возврата:\n"
        "  СОЗ, торги через 3 мес.          → +90 дней\n"
        "  Проиграли, заказчик интересный   → +180 дней\n"
        "  Торги отменены (перенесут)        → +45 дней\n"
        "  Выиграли, проверить контракт      → +180 дней\n\n"
        "⏰ Микросервис перенесёт в архивную воронку ночью (если все поля заполнены)."
    ),
}


def get_status_note(status_key: str) -> str:
    """Вернуть текст заметки для статуса. Возвращает пустую строку если шаблон не найден."""
    return STATUS_NOTE_TEMPLATES.get(status_key, "")


def get_status_note_map() -> dict:
    """Маппинг status_id → текст заметки."""
    return {
        ActiveStatuses.LLM_RECOGNIZED:  STATUS_NOTE_TEMPLATES["LLM_RECOGNIZED"],
        ActiveStatuses.CHECK_EMPLOYEE2: STATUS_NOTE_TEMPLATES["CHECK_EMPLOYEE2"],
        ActiveStatuses.SOZ_CALL:        STATUS_NOTE_TEMPLATES["SOZ_CALL"],
        ActiveStatuses.SOZ_WAIT:        STATUS_NOTE_TEMPLATES["SOZ_WAIT"],
        ActiveStatuses.PURCHASING:      STATUS_NOTE_TEMPLATES["PURCHASING"],
        ActiveStatuses.KP_PREPARING:    STATUS_NOTE_TEMPLATES["KP_PREPARING"],
        ActiveStatuses.KP_SENT_DEALER:  STATUS_NOTE_TEMPLATES["KP_SENT_DEALER"],
        ActiveStatuses.DEALER_DECISION: STATUS_NOTE_TEMPLATES["DEALER_DECISION"],
        ActiveStatuses.BIDDING:         STATUS_NOTE_TEMPLATES["BIDDING"],
        ActiveStatuses.PRODUCTION:      STATUS_NOTE_TEMPLATES["PRODUCTION"],
        ActiveStatuses.TO_ARCHIVE:      STATUS_NOTE_TEMPLATES["TO_ARCHIVE"],
    }


# ═══════════════════════════════════════════════════════════════════
# МЕТКИ ПРИОРИТЕТА В НАЗВАНИИ СДЕЛКИ
# ═══════════════════════════════════════════════════════════════════
# enum_id → префикс названия сделки

PRIORITY_LABELS = {
    215673: "🔴 СРОЧНО",   # Р1 — Срочно
    215675: "🟡 ВАЖНО",    # Р2 — Важно
    215677: "🟢 ПЛАН",      # Р3 — Плановый
    215679: "⚪ АРХИВ",     # Р4 — Архив
}


def build_lead_name(
    priority_enum_id: int,
    customer: str,
    deadline_str: str,
    situation_type: str = "",
    product_hint: str = "",
) -> str:
    """
    Строит короткое название сделки для канбан-карточки (~31 символ).
    Формат: "🔴 СРОЧНО — КБП Шипунова — 08.06"
    Заказчик сокращается до 20 символов чтобы всё влезло в канбан-карточку.
    """
    prefix = PRIORITY_LABELS.get(priority_enum_id, "⚪")
    customer_short = customer[:20].strip() if customer else ""
    parts = [prefix]
    if customer_short:
        parts.append(customer_short)
    if deadline_str:
        parts.append(deadline_str)
    return " — ".join(parts)


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
