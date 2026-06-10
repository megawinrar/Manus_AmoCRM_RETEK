"""
Yandex Disk HTTP client adapter.
"""

import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

class YaDiskClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://cloud-api.yandex.net/v1/disk"
        self.headers = {"Authorization": f"OAuth {token}"}

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(method, url, headers=self.headers, timeout=15, **kwargs)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"YaDisk API Error: {method} {endpoint} -> {str(e)}")
            raise

    def get_public_folder_items(self, public_key: str, path: str = "") -> list[dict]:
        """Получить список файлов из публичной папки (по ссылке)."""
        params = {"public_key": public_key, "limit": 100}
        if path:
            params["path"] = path
            
        try:
            data = self._request("GET", "/public/resources", params=params)
            return data.get("_embedded", {}).get("items", [])
        except Exception:
            return []

    def get_public_download_url(self, public_key: str, path: str) -> Optional[str]:
        """Получить прямой URL для скачивания файла из публичной папки."""
        params = {"public_key": public_key, "path": path}
        try:
            data = self._request("GET", "/public/resources/download", params=params)
            return data.get("href")
        except Exception:
            return None

    def get_folder_items(self, path: str) -> list[dict]:
        """Получить список файлов из внутренней папки."""
        params = {"path": path, "limit": 100}
        try:
            data = self._request("GET", "/resources", params=params)
            return data.get("_embedded", {}).get("items", [])
        except Exception:
            return []

    def get_download_url(self, path: str) -> Optional[str]:
        """Получить прямой URL для скачивания файла из внутренней папки."""
        params = {"path": path}
        try:
            data = self._request("GET", "/resources/download", params=params)
            return data.get("href")
        except Exception:
            return None

    def download_file(self, download_url: str, save_path: str) -> bool:
        """Скачать файл по прямому URL."""
        try:
            response = requests.get(download_url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"Error downloading file {download_url}: {e}")
            return False
