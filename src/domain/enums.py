"""
Enums for RETEK amoCRM.
"""

class Priority:
    P1 = "Р1 — Срочно"
    P2 = "Р2 — Быстрые деньги"
    P3 = "Р3 — Средние деньги"
    P4 = "Р4 — Наблюдаем"


class Direction:
    HSS_01 = "HSS-01 — Каталожный быстрорез ГОСТ"
    HSS_02 = "HSS-02 — Каталожный быстрорез импорт (аналог)"
    HSS_03 = "HSS-03 — Каталожный быстрорез импорт (оригинал)"
    HSS_04 = "HSS-04 — Каталожный быстрорез иностранного бренда (Dormer)"
    HSS_05 = "HSS-05 — Каталожный быстрорез иностранного бренда (Walter, Guhring)"
    HSS_06 = "HSS-06 — Спец. быстрорез по чертежам"
    CARB_01 = "CARB-01 — Твердосплав + ГИСП"
    CARB_02 = "CARB-02 — Твердосплав без ГИСП"
    CARB_03 = "CARB-03 — Спец. твердосплав по чертежам"
    CARB_04 = "CARB-04 — Спец. твердосплав по чертежам + ГИСП"
    INSERT_01 = "INSERT-01 — Пластины (оригинал)"
    INSERT_02 = "INSERT-02 — Пластины (аналог)"
    INSERT_03 = "INSERT-03 — Сборная заявка"
    GAUGE_01 = "GAUGE-01 — Резьбовые калибры"
    GAUGE_02 = "GAUGE-02 — Скобы / гладкие калибры"
    DIAMOND = "DIAMOND — Алмазный инструмент"
    OUT_OF_SCOPE = "Не наш ассортимент"


class SituationType:
    SOZ = "СОЗ"
    REAL_TENDER = "Реальные торги"
    STANDARD = "Стандарт"
    UNCLEAR = "Неясно"


class Pipelines:
    ACTIVE = 9187310
    ARCHIVE_DIRECTIONS = 9187326
    ARCHIVE_SOZ = 9187342


class ActiveStatuses:
    # 1. LLM распознал
    LLM_RECOGNIZED = 74431298
    # 2. Проверка Сотрудника 2
    CHECK_EMPLOYEE2 = 74431302
    # 3. СОЗ — звонок
    SOZ_CALL = 74431306
    # 4. СОЗ — ждём дату
    SOZ_WAIT = 74431310
    # 5. Передано в закупку
    PURCHASING = 74431314
    # 6. КП готовится
    KP_PREPARING = 74431318
    # 7. КП передано дилеру
    KP_SENT_DEALER = 74431322
    # 8. Решение дилера
    DEALER_DECISION = 74431326
    # 9. Торги
    BIDDING = 74431330
    # 10. Производство
    PRODUCTION = 74431334
    # 11. К архивированию
    TO_ARCHIVE = 74431338


class ArchiveDirectionsStatuses:
    SPEC_DRAWING = 74431410
    HSS_GOST = 74431414
    CARBIDE = 74431418
    DIAMOND = 74431422
    OUT_OF_SCOPE = 74431426
    DUPLICATES = 74431430
    NEEDS_CHECK = 74431434


class ArchiveSozStatuses:
    WAITING_REAL_TENDER = 74431498
    TO_CALL = 74431502
    REPEAT_30_DAYS = 74431506
    REPEAT_90_DAYS = 74431510
    INTERESTING_FACTORY = 74431514
    IRRELEVANT = 74431518


class Fields:
    # ID кастомных полей
    PRIORITY = 388147
    CUSTOMER = 388149
    NMC = 388151
    SITUATION_TYPE = 388153
    DIRECTION = 388155
    SUB_DIRECTION = 388157
    CLOSE_REASON = 388159
    ARCHIVE_DEST_LLM = 388161
    ARCHIVE_DEST_FINAL = 388163
    RETURN_DATE = 388165
    NEXT_ACTION = 388167
    INN = 388169
    DEADLINE = 388171
    TENDER_LINK = 388173
    FILE_HASH = 388175
    FILE_SIZE = 388177
    YADISK_LINK = 388179
    FILES_LIST = 388181
    DEALER_DECISION = 388183
    DEALER_CHANNEL = 388185
    DEALER_MARGIN = 388187
    MANUFACTURER = 388189
    RETEK_MARGIN = 388191
    PAYMENT_TERMS = 388193
    DELIVERY_TERMS = 388195
    DELIVERY_ADDRESS = 388197
    LOGISTICS_COST = 388199
    WINNER = 388201
    WINNER_INN = 388203
    WINNER_PRICE = 388205
    OUR_PRICE = 388207
    OUR_POSITION = 388209


class Users:
    EMPLOYEE_1_PARSER = 12431610
    EMPLOYEE_2_SALES = 12431614
    EMPLOYEE_3_BUYER = 12431618
    BOT = 12431622


# ВАЖНО: amoCRM удаляет 4-байтовые UTF-8 символы (эмодзи) из названия сделки.
# Используем текстовые маркеры [P1], [P2], [P3], [P4].
PRIORITY_LABELS = {
    215673: "[P1] СРОЧНО",   # Р1 — Срочно
    215675: "[P2]",           # Р2 — Быстрые Деньги
    215677: "[P3]",           # Р3 — Средние Деньги
    215679: "[P4]",           # Р4 — Наблюдаем
}

# Цветные теги приоритета (видны на канбан-доске как цветная точка)
PRIORITY_TAG_IDS = {
    215673: 32309,  # P1_СРОЧНО  — цвет FF8F92 (красный)
    215675: 32303,  # P2_Быстрые — цвет FFC8C8 (розовый)
    215677: 32305,  # P3_Средние — цвет DDEBB5 (зелёный)
    215679: 32307,  # P4_Наблюдаем — цвет D0D0D0 (серый)
}
