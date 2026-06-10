"""
AmoCRM HTTP client adapter.
"""

import os
import time
import logging
import requests
from typing import Optional, Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class AmoClient:
    def __init__(self, subdomain: str, access_token: str):
        self.subdomain = subdomain
        self.access_token = access_token
        self.base_url = f"https://{subdomain}.amocrm.ru/api/v4"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        self.dry_run = os.getenv("DRY_RUN", "1") == "1"

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        url = f"{self.base_url}{endpoint}"
        
        # Dry run protection for mutating methods
        if self.dry_run and method.upper() in ["POST", "PATCH", "DELETE"]:
            logger.info(f"[DRY RUN] {method} {url} kwargs={kwargs}")
            return {"_dry_run": True, "id": 9999999}

        try:
            response = requests.request(method, url, headers=self.headers, timeout=10, **kwargs)
            if response.status_code == 204:
                return {}
            
            response.raise_for_status()
            
            # AmoCRM can return 200 with empty body
            if not response.text:
                return {}
                
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"AmoCRM API Error: {method} {endpoint} -> {e.response.status_code} {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"AmoCRM Network Error: {method} {endpoint} -> {str(e)}")
            raise

    def get_lead(self, lead_id: int) -> dict:
        return self._request("GET", f"/leads/{lead_id}?with=custom_fields")

    def get_leads(self, query: str = None, pipeline_id: int = None, limit: int = 50, page: int = 1) -> list:
        params = {"limit": limit, "page": page, "with": "custom_fields"}
        if query:
            params["query"] = query
        if pipeline_id:
            params["filter[pipeline_id]"] = pipeline_id
            
        data = self._request("GET", "/leads", params=params)
        return data.get("_embedded", {}).get("leads", [])

    def create_lead(self, name: str, pipeline_id: int, status_id: int, custom_fields: list = None) -> int:
        payload = {
            "name": name,
            "pipeline_id": pipeline_id,
            "status_id": status_id,
        }
        if custom_fields:
            payload["custom_fields_values"] = custom_fields

        data = self._request("POST", "/leads", json=[payload])
        if self.dry_run:
            return 9999999
            
        return data.get("_embedded", {}).get("leads", [{}])[0].get("id", 0)

    def update_lead(self, lead_id: int, status_id: int = None, responsible_user_id: int = None, custom_fields: list = None) -> bool:
        payload = {"id": lead_id}
        if status_id is not None:
            payload["status_id"] = status_id
        if responsible_user_id is not None:
            payload["responsible_user_id"] = responsible_user_id
        if custom_fields is not None:
            payload["custom_fields_values"] = custom_fields

        data = self._request("PATCH", "/leads", json=[payload])
        if self.dry_run:
            return True
            
        return bool(data.get("_embedded", {}).get("leads"))

    def add_note(self, entity_id: int, text: str, entity_type: str = "leads") -> int:
        payload = {
            "entity_id": entity_id,
            "note_type": "common",
            "params": {"text": text}
        }
        data = self._request("POST", f"/{entity_type}/notes", json=[payload])
        if self.dry_run:
            return 9999999
            
        return data.get("_embedded", {}).get("notes", [{}])[0].get("id", 0)

    def add_task(self, entity_id: int, text: str, complete_till: int, responsible_user_id: int = None, entity_type: str = "leads") -> int:
        payload = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "text": text,
            "complete_till": complete_till,
        }
        if responsible_user_id:
            payload["responsible_user_id"] = responsible_user_id

        data = self._request("POST", "/tasks", json=[payload])
        if self.dry_run:
            return 9999999
            
        return data.get("_embedded", {}).get("tasks", [{}])[0].get("id", 0)
