"""
auth.py — OAuth 2.0 авторизация для amoCRM API
RETEK Archiver Integration

Использование:
  1. Первичная авторизация (получение authorization_code):
     python3 auth.py --get-code

  2. Обмен кода на токены:
     python3 auth.py --exchange-code CODE

  3. Обновление access_token через refresh_token:
     python3 auth.py --refresh
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env из корня проекта
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

AMO_DOMAIN       = os.getenv("AMO_DOMAIN", "tokutools.amocrm.ru")
CLIENT_ID        = os.getenv("AMO_CLIENT_ID")
CLIENT_SECRET    = os.getenv("AMO_CLIENT_SECRET")
REDIRECT_URI     = f"https://{AMO_DOMAIN}/"


def get_authorization_url() -> str:
    """Возвращает URL для получения authorization_code."""
    return (
        f"https://{AMO_DOMAIN}/oauth?client_id={CLIENT_ID}"
        f"&state=retek_archiver&mode=post_message"
    )


def exchange_code_for_tokens(code: str) -> dict:
    """Обменивает authorization_code на access_token и refresh_token."""
    url = f"https://{AMO_DOMAIN}/oauth2/access_token"
    payload = {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    _save_tokens(data)
    return data


def refresh_access_token() -> dict:
    """Обновляет access_token с помощью refresh_token."""
    refresh_token = os.getenv("AMO_REFRESH_TOKEN")
    if not refresh_token:
        raise ValueError("AMO_REFRESH_TOKEN не задан в .env")

    url = f"https://{AMO_DOMAIN}/oauth2/access_token"
    payload = {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "redirect_uri":  REDIRECT_URI,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    _save_tokens(data)
    return data


def get_valid_token() -> str:
    """
    Возвращает действующий access_token.
    Автоматически обновляет через refresh_token если истёк.
    """
    access_token  = os.getenv("AMO_ACCESS_TOKEN")
    expires_at    = float(os.getenv("AMO_TOKEN_EXPIRES_AT", "0"))

    if not access_token:
        raise ValueError("AMO_ACCESS_TOKEN не задан. Запустите: python3 auth.py --exchange-code CODE")

    # Обновляем за 5 минут до истечения
    if time.time() > expires_at - 300:
        print("[auth] Access token истекает, обновляю через refresh_token...")
        data = refresh_access_token()
        access_token = data["access_token"]

    return access_token


def _save_tokens(data: dict):
    """Сохраняет токены обратно в .env файл."""
    access_token  = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")
    expires_in    = int(data.get("expires_in", 86400))
    expires_at    = time.time() + expires_in

    # Читаем текущий .env
    env_content = env_path.read_text(encoding="utf-8")

    def replace_or_append(content: str, key: str, value: str) -> str:
        lines = content.splitlines()
        found = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}")
        return "\n".join(new_lines) + "\n"

    env_content = replace_or_append(env_content, "AMO_ACCESS_TOKEN",  access_token)
    env_content = replace_or_append(env_content, "AMO_REFRESH_TOKEN", refresh_token)
    env_content = replace_or_append(env_content, "AMO_TOKEN_EXPIRES_AT", str(expires_at))

    env_path.write_text(env_content, encoding="utf-8")

    # Обновляем переменные в текущем процессе
    os.environ["AMO_ACCESS_TOKEN"]    = access_token
    os.environ["AMO_REFRESH_TOKEN"]   = refresh_token
    os.environ["AMO_TOKEN_EXPIRES_AT"] = str(expires_at)

    print(f"[auth] Токены сохранены. Истекают через {expires_in // 3600}ч.")
    print(f"[auth] access_token: {access_token[:20]}...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "--get-code":
        url = get_authorization_url()
        print(f"\nОткройте эту ссылку в браузере и авторизуйте интеграцию:\n\n{url}\n")
        print("После авторизации скопируйте code= из URL и запустите:")
        print("  python3 auth.py --exchange-code <CODE>\n")

    elif cmd == "--exchange-code":
        if len(sys.argv) < 3:
            print("Укажите код: python3 auth.py --exchange-code <CODE>")
            sys.exit(1)
        code = sys.argv[2]
        data = exchange_code_for_tokens(code)
        print(f"\n[OK] Авторизация успешна!")
        print(f"access_token:  {data['access_token'][:30]}...")
        print(f"refresh_token: {data['refresh_token'][:30]}...")

    elif cmd == "--refresh":
        data = refresh_access_token()
        print(f"\n[OK] Токен обновлён!")
        print(f"access_token: {data['access_token'][:30]}...")

    else:
        print(f"Неизвестная команда: {cmd}")
        print(__doc__)
        sys.exit(1)
