"""
LLM Классификатор тендеров — llm_classifier.py

Использует Яндекс GPT (через OpenAI-совместимый API) для:
1. Классификации входящих тендеров (Действие 1)
2. Определения архивного назначения (Действие 2)
3. (Будущее) Распознавания контекста из чата карточки (Действие 3)

RAG-подход: при каждом вызове подаём CONTEXT_FULL.md как system prompt,
чтобы LLM действовала строго по правилам компании.

Режим обучения: LLM всегда работает, но в режиме обучения
результаты записываются в лог и НЕ применяются автоматически.
После обкатки — переключаем в боевой режим.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════

YANDEX_GPT_API_KEY = os.getenv("YANDEX_GPT_API_KEY", "")
YANDEX_GPT_FOLDER_ID = os.getenv("YANDEX_GPT_FOLDER_ID", "")
YANDEX_GPT_MODEL = os.getenv("YANDEX_GPT_MODEL", "yandexgpt/latest")
YANDEX_GPT_BASE_URL = "https://ai.api.cloud.yandex.net/v1"

# Режим работы LLM
# training — LLM работает, результаты логируются, но НЕ применяются
# production — LLM работает и результаты применяются автоматически
LLM_MODE = os.getenv("LLM_MODE", "training")

# Путь к контекстным файлам (RAG)
DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
CONTEXT_FILE = DOCS_DIR / "CONTEXT_FULL.md"
FIELDS_FILE = DOCS_DIR / "amocrm_fields_and_logic.md"

# Лог результатов LLM (для режима обучения)
LLM_LOG_DIR = os.getenv("LLM_LOG_DIR", "data/llm_logs")


# ═══════════════════════════════════════════════════════════════════
# СИСТЕМНЫЙ ПРОМПТ (RAG-контекст)
# ═══════════════════════════════════════════════════════════════════

def load_system_context() -> str:
    """Загрузить контекст из .md файлов для system prompt."""
    context_parts = []

    if CONTEXT_FILE.exists():
        context_parts.append(CONTEXT_FILE.read_text(encoding="utf-8"))

    if FIELDS_FILE.exists():
        context_parts.append(FIELDS_FILE.read_text(encoding="utf-8"))

    return "\n\n---\n\n".join(context_parts)


SYSTEM_PROMPT_CLASSIFIER = """Ты — AI-ассистент компании RETEK, специализирующейся на торговле режущим инструментом через тендерные площадки.

Твоя задача — классифицировать входящий тендер на основе названия папки и содержимого файлов.

КОНТЕКСТ КОМПАНИИ:
{context}

ИНСТРУКЦИЯ:
Проанализируй название папки тендера и список файлов. Определи:
1. Приоритет (Р1/Р2/Р3/Р4)
2. Тип ситуации (СОЗ / Запрос котировок / реальные торги / Неясно / Не наш ассортимент)
3. Направление (SPEC-DRAWING / HSS-STANDARD / CARBIDE-STANDARD / DIAMOND-STANDARD / SOZ-DEVELOPMENT / REAL-TENDER / OUT-OF-SCOPE / ARCHIVE-LEAD)
4. Подтип направления (если SPEC-DRAWING)
5. Заказчик (извлечь из названия)
6. Краткое описание предмета закупки
7. Уверенность (0.0 — 1.0)
8. Комментарий (почему так решил)

ПРАВИЛА ПРИОРИТЕТОВ:
- Р1 (Срочно): горящие сроки, крупная сумма, стратегический заказчик
- Р2 (Быстрые Деньги): реальные торги с понятным предметом, средняя сумма
- Р3 (Средние Деньги): стандартные торги, небольшие объёмы
- Р4 (Наблюдаем): СОЗ без конкретики, мелочь, не наш ассортимент

ПРАВИЛА НАПРАВЛЕНИЙ:
- Если в названии есть "чертеж", "ТЗ", "эскиз", "образец" → SPEC-DRAWING
- Если "HSS", "ГОСТ", "метчик", "сверло", "развертка" (стандарт) → HSS-STANDARD
- Если "твердосплав", "пластина", "фреза твердосплавная" → CARBIDE-STANDARD
- Если "алмаз" → DIAMOND-STANDARD
- Если "СОЗ", "сбор", "ждём" → SOZ-DEVELOPMENT
- Если "калибр", "скоба", "не наш" → OUT-OF-SCOPE
- Если "борфреза", "аналог" → проверить, может быть CARBIDE-STANDARD

ПРАВИЛА ТИПА СИТУАЦИИ:
- Если в названии "СОЗ" → СОЗ
- Если есть конкретные файлы ИоЗ, ТЗ, спецификация → Запрос котировок / реальные торги
- Если "калибры", "не интересно", "не наш" → Не наш ассортимент
- Если непонятно → Неясно

Ответь СТРОГО в формате JSON:
{{
    "priority": "Р1|Р2|Р3|Р4",
    "situation_type": "СОЗ|Запрос котировок / реальные торги|Неясно|Не наш ассортимент",
    "direction": "SPEC-DRAWING|HSS-STANDARD|CARBIDE-STANDARD|DIAMOND-STANDARD|SOZ-DEVELOPMENT|REAL-TENDER|OUT-OF-SCOPE|ARCHIVE-LEAD",
    "sub_direction": "твердосплав по чертежам|быстрорез по чертежам|алмазный по чертежам|прочий инструмент по ТЗ|инструмент по эскизу / образцу|null",
    "customer": "название заказчика",
    "product_description": "краткое описание предмета закупки (до 50 слов)",
    "confidence": 0.85,
    "comment": "обоснование решения"
}}
"""

SYSTEM_PROMPT_ARCHIVE = """Ты — AI-ассистент компании RETEK. Твоя задача — определить архивное назначение для карточки тендера.

КОНТЕКСТ КОМПАНИИ:
{context}

ИНСТРУКЦИЯ:
На основе полей карточки (направление, подтип, причина закрытия, история) определи:
1. Архивное назначение итоговое — в какую архивную воронку отправить карточку

ВАРИАНТЫ АРХИВНОГО НАЗНАЧЕНИЯ:
- Архив — направления / Специнструмент по чертежам
- Архив — направления / HSS ГОСТ
- Архив — направления / Твердосплав
- Архив — направления / Алмазный
- Архив — направления / Не наш ассортимент
- Архив — направления / Дубли / мусор
- Архив — направления / Требуется проверка
- Архив — СОЗ / Ждём реальные торги
- Архив — СОЗ / К обзвону
- Архив — СОЗ / Повторить через 30 дней
- Архив — СОЗ / Повторить через 90 дней
- Архив — СОЗ / Интересный завод
- Архив — СОЗ / Неактуально

ПРАВИЛА:
- Если направление = SPEC-DRAWING → "Архив — направления / Специнструмент по чертежам"
- Если направление = HSS-STANDARD → "Архив — направления / HSS ГОСТ"
- Если направление = CARBIDE-STANDARD → "Архив — направления / Твердосплав"
- Если направление = DIAMOND-STANDARD → "Архив — направления / Алмазный"
- Если направление = OUT-OF-SCOPE → "Архив — направления / Не наш ассортимент"
- Если тип ситуации = СОЗ и причина = "Ждём реальные торги" → "Архив — СОЗ / Ждём реальные торги"
- Если тип ситуации = СОЗ и нужен обзвон → "Архив — СОЗ / К обзвону"
- Если заказчик интересный и торги будут → "Архив — СОЗ / Интересный завод"
- Если непонятно → "Архив — направления / Требуется проверка"

Ответь СТРОГО в формате JSON:
{{
    "archive_destination": "точное значение из списка выше",
    "confidence": 0.85,
    "comment": "обоснование решения"
}}
"""


# ═══════════════════════════════════════════════════════════════════
# КЛИЕНТ ЯНДЕКС GPT
# ═══════════════════════════════════════════════════════════════════

class YandexGPTClient:
    """Клиент для Яндекс GPT через OpenAI-совместимый API."""

    def __init__(self):
        self.api_key = YANDEX_GPT_API_KEY
        self.folder_id = YANDEX_GPT_FOLDER_ID
        self.model = f"gpt://{self.folder_id}/{YANDEX_GPT_MODEL}"
        self.base_url = YANDEX_GPT_BASE_URL
        self._client = None

    @property
    def client(self):
        """Ленивая инициализация OpenAI клиента."""
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    default_headers={"x-folder-id": self.folder_id},
                )
            except ImportError:
                raise ImportError("Установите openai: pip install openai")
        return self._client

    def is_configured(self) -> bool:
        """Проверить, настроен ли клиент."""
        return bool(self.api_key and self.folder_id)

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Optional[str]:
        """
        Отправить запрос в Яндекс GPT.
        
        Returns: текст ответа или None при ошибке
        """
        if not self.is_configured():
            logger.warning("Яндекс GPT не настроен (нет API_KEY или FOLDER_ID)")
            return None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Ошибка Яндекс GPT: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════
# ДЕЙСТВИЕ 1: КЛАССИФИКАЦИЯ ТЕНДЕРА
# ═══════════════════════════════════════════════════════════════════

def classify_tender(
    folder_name: str,
    date_folder: str,
    files: list[str],
    file_contents: Optional[dict[str, str]] = None,
) -> dict:
    """
    Классифицировать тендер через Яндекс GPT.
    
    Args:
        folder_name: название папки тендера (напр. "Gesac - 86 поз.")
        date_folder: дата папки (напр. "09.06.2026")
        files: список путей к скачанным файлам
        file_contents: опционально — извлечённый текст из файлов
        
    Returns:
        Словарь с классификацией или ошибкой
    """
    gpt = YandexGPTClient()

    if not gpt.is_configured():
        # Fallback: rule-based классификация по названию папки
        logger.info("GPT не настроен, используем rule-based классификацию")
        return classify_by_rules(folder_name, files)

    # Формируем контекст
    context = load_system_context()
    system_prompt = SYSTEM_PROMPT_CLASSIFIER.format(context=context)

    # Формируем запрос
    file_names = [os.path.basename(f) for f in files]
    user_message = (
        f"Папка тендера: {folder_name}\n"
        f"Дата загрузки: {date_folder}\n"
        f"Файлы ({len(file_names)} шт.):\n"
        + "\n".join(f"  - {name}" for name in file_names)
    )

    # Если есть содержимое файлов — добавляем
    if file_contents:
        user_message += "\n\nИзвлечённый текст из файлов:\n"
        for fname, content in file_contents.items():
            # Ограничиваем длину каждого файла
            truncated = content[:2000] if len(content) > 2000 else content
            user_message += f"\n--- {fname} ---\n{truncated}\n"

    # Запрос к GPT
    response_text = gpt.complete(system_prompt, user_message)

    if not response_text:
        logger.warning("GPT не ответил, используем rule-based")
        return classify_by_rules(folder_name, files)

    # Парсим JSON из ответа
    result = parse_json_response(response_text)

    if result:
        result["source"] = "yandex_gpt"
        result["mode"] = LLM_MODE
        # Логируем результат
        log_llm_result("classify", folder_name, user_message, response_text, result)
    else:
        logger.warning(f"Не удалось распарсить ответ GPT: {response_text[:200]}")
        result = classify_by_rules(folder_name, files)

    return result


# ═══════════════════════════════════════════════════════════════════
# ДЕЙСТВИЕ 2: ОПРЕДЕЛЕНИЕ АРХИВНОГО НАЗНАЧЕНИЯ
# ═══════════════════════════════════════════════════════════════════

def determine_archive_destination(
    direction: str,
    sub_direction: Optional[str],
    situation_type: str,
    close_reason: str,
    customer: str,
    lead_name: str,
) -> dict:
    """
    Определить архивное назначение через Яндекс GPT.
    
    Args:
        direction: направление (SPEC-DRAWING, HSS-STANDARD, ...)
        sub_direction: подтип направления
        situation_type: тип ситуации
        close_reason: причина закрытия
        customer: заказчик
        lead_name: название сделки
        
    Returns:
        {"archive_destination": "...", "confidence": 0.9, "comment": "..."}
    """
    gpt = YandexGPTClient()

    if not gpt.is_configured():
        return determine_archive_by_rules(direction, situation_type)

    context = load_system_context()
    system_prompt = SYSTEM_PROMPT_ARCHIVE.format(context=context)

    user_message = (
        f"Карточка тендера:\n"
        f"  Название: {lead_name}\n"
        f"  Заказчик: {customer}\n"
        f"  Направление: {direction}\n"
        f"  Подтип: {sub_direction or 'не указан'}\n"
        f"  Тип ситуации: {situation_type}\n"
        f"  Причина закрытия: {close_reason}\n\n"
        f"Определи архивное назначение."
    )

    response_text = gpt.complete(system_prompt, user_message)

    if not response_text:
        return determine_archive_by_rules(direction, situation_type)

    result = parse_json_response(response_text)

    if result:
        result["source"] = "yandex_gpt"
        result["mode"] = LLM_MODE
        log_llm_result("archive", lead_name, user_message, response_text, result)
    else:
        result = determine_archive_by_rules(direction, situation_type)

    return result


# ═══════════════════════════════════════════════════════════════════
# RULE-BASED FALLBACK (когда GPT недоступен)
# ═══════════════════════════════════════════════════════════════════

def classify_by_rules(folder_name: str, files: list[str]) -> dict:
    """
    Классификация по правилам (без LLM).
    Анализирует название папки и имена файлов.
    """
    name_lower = folder_name.lower()
    file_names_lower = " ".join(os.path.basename(f).lower() for f in files)

    # Определяем направление
    direction = "REAL-TENDER"
    sub_direction = None

    if "калибр" in name_lower or "не интересно" in name_lower or "не наш" in name_lower:
        direction = "OUT-OF-SCOPE"
    elif "соз" in name_lower or "сбор" in name_lower:
        direction = "SOZ-DEVELOPMENT"
    elif "алмаз" in name_lower:
        direction = "DIAMOND-STANDARD"
    elif "твердосплав" in name_lower or "пластин" in name_lower:
        direction = "CARBIDE-STANDARD"
    elif "hss" in name_lower or "гост" in name_lower or "метчик" in name_lower:
        direction = "HSS-STANDARD"
    elif "чертеж" in name_lower or "тз" in name_lower:
        direction = "SPEC-DRAWING"
    elif "борфрез" in name_lower:
        direction = "CARBIDE-STANDARD"
    elif "фреза" in name_lower or "зенкер" in name_lower or "сверл" in name_lower:
        direction = "CARBIDE-STANDARD"
    elif "долбяк" in name_lower or "червячн" in name_lower:
        direction = "SPEC-DRAWING"

    # Определяем тип ситуации
    situation_type = "Запрос котировок / реальные торги"
    if "соз" in name_lower:
        situation_type = "СОЗ"
    elif "калибр" in name_lower or "не интересно" in name_lower:
        situation_type = "Не наш ассортимент"
    elif "иоз" in file_names_lower or "извещение" in file_names_lower:
        situation_type = "Запрос котировок / реальные торги"

    # Определяем приоритет
    priority = "Р3"
    if "горящ" in name_lower or "срочн" in name_lower:
        priority = "Р1"
    elif direction == "OUT-OF-SCOPE" or situation_type == "Не наш ассортимент":
        priority = "Р4"
    elif "соз" in name_lower:
        priority = "Р3"
    elif "350к" in name_lower or "190 поз" in name_lower or "86 поз" in name_lower:
        priority = "Р2"

    # Извлекаем заказчика
    customer = extract_customer_from_name(folder_name)

    return {
        "priority": priority,
        "situation_type": situation_type,
        "direction": direction,
        "sub_direction": sub_direction,
        "customer": customer,
        "product_description": folder_name,
        "confidence": 0.6,
        "comment": "Rule-based классификация (GPT недоступен)",
        "source": "rules",
        "mode": LLM_MODE,
    }


def determine_archive_by_rules(direction: str, situation_type: str) -> dict:
    """Определить архивное назначение по правилам."""
    mapping = {
        "SPEC-DRAWING": "Архив — направления / Специнструмент по чертежам",
        "HSS-STANDARD": "Архив — направления / HSS ГОСТ",
        "CARBIDE-STANDARD": "Архив — направления / Твердосплав",
        "DIAMOND-STANDARD": "Архив — направления / Алмазный",
        "OUT-OF-SCOPE": "Архив — направления / Не наш ассортимент",
        "SOZ-DEVELOPMENT": "Архив — СОЗ / Ждём реальные торги",
        "ARCHIVE-LEAD": "Архив — СОЗ / Неактуально",
    }

    # СОЗ всегда в архив СОЗ
    if situation_type == "СОЗ":
        destination = "Архив — СОЗ / Ждём реальные торги"
    else:
        destination = mapping.get(direction, "Архив — направления / Требуется проверка")

    return {
        "archive_destination": destination,
        "confidence": 0.7,
        "comment": "Rule-based определение (GPT недоступен)",
        "source": "rules",
        "mode": LLM_MODE,
    }


# ═══════════════════════════════════════════════════════════════════
# УТИЛИТЫ
# ═══════════════════════════════════════════════════════════════════

def extract_customer_from_name(folder_name: str) -> str:
    """Извлечь название заказчика из имени папки."""
    # Паттерны: "АО ОКБ ФАКЕЛ - твердосплав" → "АО ОКБ ФАКЕЛ"
    # "Gesac - 86 поз." → "Gesac"
    parts = folder_name.split(" - ")
    if parts:
        customer = parts[0].strip()
        # Убираем лишние пробелы
        return " ".join(customer.split())
    return folder_name


def parse_json_response(text: str) -> Optional[dict]:
    """Извлечь JSON из ответа LLM (может быть обёрнут в markdown)."""
    # Пробуем напрямую
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Ищем JSON в markdown блоке ```json ... ```
    import re
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Ищем первый { ... }
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def log_llm_result(
    action: str,
    identifier: str,
    prompt: str,
    response: str,
    result: dict,
):
    """Записать результат LLM в лог-файл (для режима обучения)."""
    os.makedirs(LLM_LOG_DIR, exist_ok=True)

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in identifier[:50])
    filename = f"{timestamp}_{action}_{safe_id}.json"

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "identifier": identifier,
        "mode": LLM_MODE,
        "prompt_length": len(prompt),
        "response": response,
        "parsed_result": result,
    }

    filepath = os.path.join(LLM_LOG_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(log_entry, ensure_ascii=False, indent=2, fp=f)

    logger.info(f"LLM лог записан: {filepath}")


# ═══════════════════════════════════════════════════════════════════
# ТЕСТИРОВАНИЕ
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # Тест rule-based классификации
    test_cases = [
        ("Gesac - 86 поз.", ["Gesac - 86 pos_RU.xlsx", "ИоЗ.docx"]),
        ("АО ОКБ ФАКЕЛ - твердосплав 350к руб", ["ТЗ.pdf", "спецификация.xlsx"]),
        ("ОМСКТРАНСМАШ - Долбяки СОЗ", ["запрос.docx"]),
        ("АО НПП ИСТОК ШОКИНА - Не интересно - Калибры", ["файл.doc"]),
        ("Шипунова HSS - + пример горящий", ["ИоЗ.docx", "спецификация.xlsx"]),
    ]

    for folder_name, files in test_cases:
        result = classify_by_rules(folder_name, files)
        print(f"\n{'='*60}")
        print(f"Папка: {folder_name}")
        print(f"Результат: {json.dumps(result, ensure_ascii=False, indent=2)}")
