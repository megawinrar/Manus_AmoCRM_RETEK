"""
Тесты для модуля авторизации (src/auth.py).

Покрытие:
- refresh_access_token — обновление access_token через refresh_token
- get_valid_token — получение действующего токена с авто-обновлением
- exchange_code_for_tokens — обмен authorization_code на токены
- get_authorization_url — формирование URL авторизации
- _save_tokens — сохранение токенов в .env файл

Запуск:
    pytest tests/test_auth.py -v
"""

import os
import sys
import json
import time
import pytest
from unittest.mock import patch, MagicMock

# Устанавливаем переменные окружения ДО импорта модулей
os.environ.setdefault("AMO_DOMAIN", "tokutools.amocrm.ru")
os.environ.setdefault("AMO_ACCESS_TOKEN", "test_access_token_12345")
os.environ.setdefault("AMO_REFRESH_TOKEN", "test_refresh_token_67890")
os.environ.setdefault("AMO_CLIENT_ID", "test_client_id")
os.environ.setdefault("AMO_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("AMO_TOKEN_EXPIRES_AT", str(time.time() + 86400))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.auth import (
    refresh_access_token,
    get_valid_token,
    exchange_code_for_tokens,
    get_authorization_url,
    _save_tokens,
)


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def token_response():
    """Типичный ответ amoCRM при обновлении токена."""
    return {
        "token_type": "Bearer",
        "expires_in": 86400,
        "access_token": "new_access_token_abc123",
        "refresh_token": "new_refresh_token_def456",
    }


@pytest.fixture
def env_file_content():
    """Содержимое .env файла."""
    return (
        "AMO_DOMAIN=tokutools.amocrm.ru\n"
        "AMO_CLIENT_ID=test_client_id\n"
        "AMO_CLIENT_SECRET=test_client_secret\n"
        "AMO_ACCESS_TOKEN=old_access_token\n"
        "AMO_REFRESH_TOKEN=old_refresh_token\n"
        "AMO_TOKEN_EXPIRES_AT=1700000000\n"
    )


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ get_authorization_url
# ═══════════════════════════════════════════════════════════════════

class TestGetAuthorizationUrl:
    """Тесты формирования URL авторизации."""

    def test_url_contains_domain(self):
        url = get_authorization_url()
        assert "tokutools.amocrm.ru" in url

    def test_url_contains_client_id(self):
        url = get_authorization_url()
        assert "test_client_id" in url

    def test_url_is_https(self):
        url = get_authorization_url()
        assert url.startswith("https://")

    def test_url_contains_oauth(self):
        url = get_authorization_url()
        assert "/oauth" in url


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ refresh_access_token
# ═══════════════════════════════════════════════════════════════════

class TestRefreshAccessToken:
    """Тесты обновления access_token."""

    @patch("src.auth._save_tokens")
    @patch("src.auth.requests.post")
    def test_refresh_success(self, mock_post, mock_save, token_response):
        """Успешное обновление токена."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = token_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"AMO_REFRESH_TOKEN": "valid_refresh"}):
            result = refresh_access_token()

        assert result["access_token"] == "new_access_token_abc123"
        assert result["refresh_token"] == "new_refresh_token_def456"
        mock_save.assert_called_once_with(token_response)

    def test_refresh_no_refresh_token_raises(self):
        """Ошибка если AMO_REFRESH_TOKEN не задан."""
        with patch.dict(os.environ, {"AMO_REFRESH_TOKEN": ""}, clear=False):
            os.environ.pop("AMO_REFRESH_TOKEN", None)
            with pytest.raises(ValueError, match="AMO_REFRESH_TOKEN"):
                refresh_access_token()
        # Restore
        os.environ["AMO_REFRESH_TOKEN"] = "test_refresh_token_67890"

    @patch("src.auth.requests.post")
    def test_refresh_invalid_token_401(self, mock_post):
        """Ошибка при невалидном refresh_token (401)."""
        import requests as req
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status.side_effect = req.exceptions.HTTPError("401")
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"AMO_REFRESH_TOKEN": "bad_token"}):
            with pytest.raises(req.exceptions.HTTPError):
                refresh_access_token()

    @patch("src.auth.requests.post")
    def test_refresh_network_error(self, mock_post):
        """Ошибка сети при обновлении."""
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("Connection refused")

        with patch.dict(os.environ, {"AMO_REFRESH_TOKEN": "valid_token"}):
            with pytest.raises(req.exceptions.ConnectionError):
                refresh_access_token()

    @patch("src.auth.requests.post")
    def test_refresh_timeout(self, mock_post):
        """Таймаут при обновлении."""
        import requests as req
        mock_post.side_effect = req.exceptions.Timeout("Timed out")

        with patch.dict(os.environ, {"AMO_REFRESH_TOKEN": "valid_token"}):
            with pytest.raises(req.exceptions.Timeout):
                refresh_access_token()

    @patch("src.auth._save_tokens")
    @patch("src.auth.requests.post")
    def test_refresh_sends_correct_payload(self, mock_post, mock_save, token_response):
        """Проверка payload запроса."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = token_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with patch.dict(os.environ, {"AMO_REFRESH_TOKEN": "my_refresh"}):
            refresh_access_token()

        call_kwargs = mock_post.call_args
        payload = call_kwargs[1].get("json") or call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {}
        if not payload:
            payload = call_kwargs[1].get("json", {})
        assert payload["grant_type"] == "refresh_token"
        assert payload["refresh_token"] == "my_refresh"
        assert payload["client_id"] == "test_client_id"
        assert payload["client_secret"] == "test_client_secret"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ get_valid_token
# ═══════════════════════════════════════════════════════════════════

class TestGetValidToken:
    """Тесты получения действующего токена."""

    def test_token_not_expired(self):
        """Возвращает текущий токен если не истёк."""
        future = str(time.time() + 3600)
        with patch.dict(os.environ, {
            "AMO_ACCESS_TOKEN": "valid_token_123",
            "AMO_TOKEN_EXPIRES_AT": future,
        }):
            token = get_valid_token()
        assert token == "valid_token_123"

    @patch("src.auth.refresh_access_token")
    def test_token_expired_triggers_refresh(self, mock_refresh):
        """Истёкший токен вызывает обновление."""
        mock_refresh.return_value = {"access_token": "new_token_456"}
        past = str(time.time() - 3600)
        with patch.dict(os.environ, {
            "AMO_ACCESS_TOKEN": "old_token",
            "AMO_TOKEN_EXPIRES_AT": past,
        }):
            token = get_valid_token()
        assert token == "new_token_456"
        mock_refresh.assert_called_once()

    @patch("src.auth.refresh_access_token")
    def test_token_near_expiry_triggers_refresh(self, mock_refresh):
        """Токен близкий к истечению (< 5 мин) вызывает обновление."""
        mock_refresh.return_value = {"access_token": "refreshed"}
        near = str(time.time() + 120)  # 2 min left < 5 min threshold
        with patch.dict(os.environ, {
            "AMO_ACCESS_TOKEN": "expiring",
            "AMO_TOKEN_EXPIRES_AT": near,
        }):
            token = get_valid_token()
        assert token == "refreshed"
        mock_refresh.assert_called_once()

    def test_no_access_token_raises(self):
        """Отсутствие AMO_ACCESS_TOKEN вызывает ValueError."""
        with patch.dict(os.environ, {"AMO_ACCESS_TOKEN": ""}, clear=False):
            with pytest.raises(ValueError):
                get_valid_token()

    @patch("src.auth.refresh_access_token")
    def test_expires_at_zero_triggers_refresh(self, mock_refresh):
        """AMO_TOKEN_EXPIRES_AT=0 вызывает обновление."""
        mock_refresh.return_value = {"access_token": "new"}
        with patch.dict(os.environ, {
            "AMO_ACCESS_TOKEN": "some_token",
            "AMO_TOKEN_EXPIRES_AT": "0",
        }):
            token = get_valid_token()
        assert token == "new"
        mock_refresh.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ exchange_code_for_tokens
# ═══════════════════════════════════════════════════════════════════

class TestExchangeCodeForTokens:
    """Тесты обмена authorization_code на токены."""

    @patch("src.auth._save_tokens")
    @patch("src.auth.requests.post")
    def test_exchange_success(self, mock_post, mock_save, token_response):
        """Успешный обмен кода."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = token_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = exchange_code_for_tokens("auth_code_123")
        assert result["access_token"] == "new_access_token_abc123"
        mock_save.assert_called_once_with(token_response)

    @patch("src.auth.requests.post")
    def test_exchange_invalid_code(self, mock_post):
        """Ошибка при невалидном коде."""
        import requests as req
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.exceptions.HTTPError("400")
        mock_post.return_value = mock_resp

        with pytest.raises(req.exceptions.HTTPError):
            exchange_code_for_tokens("invalid")

    @patch("src.auth._save_tokens")
    @patch("src.auth.requests.post")
    def test_exchange_correct_payload(self, mock_post, mock_save, token_response):
        """Проверка payload."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = token_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        exchange_code_for_tokens("my_code")
        payload = mock_post.call_args[1].get("json", {})
        assert payload["grant_type"] == "authorization_code"
        assert payload["code"] == "my_code"


# ═══════════════════════════════════════════════════════════════════
# ТЕСТЫ _save_tokens
# ═══════════════════════════════════════════════════════════════════

class TestSaveTokens:
    """Тесты сохранения токенов."""

    @patch("src.auth.env_path")
    def test_save_tokens_updates_env_file(self, mock_path, env_file_content):
        """_save_tokens обновляет .env файл."""
        mock_path.read_text.return_value = env_file_content
        mock_path.write_text = MagicMock()

        _save_tokens({
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_in": 86400,
        })

        mock_path.write_text.assert_called_once()
        written = mock_path.write_text.call_args[0][0]
        assert "AMO_ACCESS_TOKEN=new_access" in written
        assert "AMO_REFRESH_TOKEN=new_refresh" in written
        assert "AMO_TOKEN_EXPIRES_AT=" in written

    @patch("src.auth.env_path")
    def test_save_tokens_updates_os_environ(self, mock_path, env_file_content):
        """_save_tokens обновляет os.environ."""
        mock_path.read_text.return_value = env_file_content
        mock_path.write_text = MagicMock()

        _save_tokens({
            "access_token": "env_token",
            "refresh_token": "env_refresh",
            "expires_in": 3600,
        })

        assert os.environ["AMO_ACCESS_TOKEN"] == "env_token"
        assert os.environ["AMO_REFRESH_TOKEN"] == "env_refresh"

    @patch("src.auth.env_path")
    def test_save_tokens_appends_missing_keys(self, mock_path):
        """_save_tokens добавляет отсутствующие ключи."""
        mock_path.read_text.return_value = "AMO_DOMAIN=tokutools.amocrm.ru\n"
        mock_path.write_text = MagicMock()

        _save_tokens({
            "access_token": "brand_new",
            "refresh_token": "brand_new_refresh",
            "expires_in": 86400,
        })

        written = mock_path.write_text.call_args[0][0]
        assert "AMO_ACCESS_TOKEN=brand_new" in written
        assert "AMO_REFRESH_TOKEN=brand_new_refresh" in written
