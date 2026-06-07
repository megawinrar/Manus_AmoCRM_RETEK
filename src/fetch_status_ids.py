"""
Утилита: получить реальные status_id из amoCRM и вывести для .env файла.

Использование:
    python3 src/fetch_status_ids.py

Результат: выводит блок переменных для .env файла.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("AMO_ACCESS_TOKEN")
DOMAIN = os.getenv("AMO_DOMAIN", "tokutools.amocrm.ru")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

PIPELINE_ACTIVE = 10984442
PIPELINE_ARCHIVE_DIRECTIONS = 10984454
PIPELINE_ARCHIVE_SOZ = 10985038


def get_statuses(pipeline_id: int) -> list[dict]:
    """Получить статусы воронки."""
    url = f"https://{DOMAIN}/api/v4/leads/pipelines/{pipeline_id}/statuses"
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code == 200:
        return r.json().get("_embedded", {}).get("statuses", [])
    print(f"  Ошибка: {r.status_code} {r.text[:100]}")
    return []


def get_users() -> list[dict]:
    """Получить пользователей."""
    url = f"https://{DOMAIN}/api/v4/users"
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code == 200:
        return r.json().get("_embedded", {}).get("users", [])
    return []


def main():
    print("=" * 60)
    print("RETEK — Получение status_id для .env")
    print("=" * 60)

    # Активная воронка
    print(f"\n# ─── Активная воронка (ID: {PIPELINE_ACTIVE}) ───")
    statuses = get_statuses(PIPELINE_ACTIVE)
    
    # Маппинг имён → env-ключей
    active_mapping = {
        "LLM распознал": "STATUS_1_LLM",
        "Проверка Сотрудника 2": "STATUS_2_CHECK",
        "СОЗ — звонок / уточнить дату": "STATUS_3_SOZ_CALL",
        "СОЗ — ждём реальный торг": "STATUS_4_SOZ_WAIT",
        "Передано в закупку / расчёт": "STATUS_5_PURCHASING",
        "КП готовится": "STATUS_6_KP_PREP",
        "КП передано дилеру": "STATUS_7_KP_DEALER",
        "Решение дилера": "STATUS_8_DEALER_DEC",
        "Передано в производство": "STATUS_9_PRODUCTION",
        "К архивированию": "STATUS_10_ARCHIVE",
    }

    for s in sorted(statuses, key=lambda x: x.get("sort", 0), reverse=True):
        name = s["name"]
        sid = s["id"]
        env_key = active_mapping.get(name, f"# UNKNOWN: {name}")
        if env_key.startswith("#"):
            print(f"  {env_key} = {sid}")
        else:
            print(f"  {env_key}={sid}")

    # Архив — Направления
    print(f"\n# ─── Архив — Направления (ID: {PIPELINE_ARCHIVE_DIRECTIONS}) ───")
    statuses = get_statuses(PIPELINE_ARCHIVE_DIRECTIONS)

    dir_mapping = {
        "Специнструмент по чертежам": "ARCH_DIR_SPEC",
        "HSS ГОСТ": "ARCH_DIR_HSS",
        "Твердосплав": "ARCH_DIR_CARBIDE",
        "Алмазный": "ARCH_DIR_DIAMOND",
        "Не наш ассортимент": "ARCH_DIR_OUT",
        "Дубли/мусор": "ARCH_DIR_DUPL",
        "Требуется проверка": "ARCH_DIR_CHECK",
    }

    for s in sorted(statuses, key=lambda x: x.get("sort", 0), reverse=True):
        name = s["name"]
        sid = s["id"]
        env_key = dir_mapping.get(name, f"# UNKNOWN: {name}")
        if env_key.startswith("#"):
            print(f"  {env_key} = {sid}")
        else:
            print(f"  {env_key}={sid}")

    # Архив — СОЗ
    print(f"\n# ─── Архив — СОЗ / развитие (ID: {PIPELINE_ARCHIVE_SOZ}) ───")
    statuses = get_statuses(PIPELINE_ARCHIVE_SOZ)

    soz_mapping = {
        "Ждём реальные торги": "ARCH_SOZ_WAIT",
        "К обзвону": "ARCH_SOZ_CALL",
        "Повторить через 30 дней": "ARCH_SOZ_30D",
        "Повторить через 90 дней": "ARCH_SOZ_90D",
        "Интересный завод": "ARCH_SOZ_FACTORY",
        "Неактуально": "ARCH_SOZ_IRRELEVANT",
    }

    for s in sorted(statuses, key=lambda x: x.get("sort", 0), reverse=True):
        name = s["name"]
        sid = s["id"]
        env_key = soz_mapping.get(name, f"# UNKNOWN: {name}")
        if env_key.startswith("#"):
            print(f"  {env_key} = {sid}")
        else:
            print(f"  {env_key}={sid}")

    # Пользователи
    print(f"\n# ─── Пользователи ───")
    users = get_users()
    for u in users:
        name = u.get("name", "?")
        uid = u["id"]
        email = u.get("email", "")
        print(f"  # {name} ({email})")
        print(f"  # USER_xxx={uid}")

    print("\n" + "=" * 60)
    print("Скопируйте нужные значения в .env файл")
    print("=" * 60)


if __name__ == "__main__":
    main()
