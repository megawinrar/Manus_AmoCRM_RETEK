"""
amoCRM API Client — обёртка для микросервиса RETEK.

Функции:
- Rate limiting (7 req/s на интеграцию)
- Retry при 429 / таймаутах
- Все CRUD-операции: сделки, задачи, примечания
- Перенос между воронками
- Поиск сделок по фильтрам
"""

import os
import time
import logging
from typing import Optional, Any
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class AmoClient:
    """Клиент amoCRM API v4 с rate limiting и retry."""

    def __init__(self, dry_run: bool = False):
        self.domain = os.getenv("AMO_DOMAIN", "tokutools.amocrm.ru")
        self.token = os.getenv("AMO_ACCESS_TOKEN", "")
        self.base_url = f"https://{self.domain}/api/v4"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.dry_run = dry_run
        self._last_request_time = 0.0
        self._min_interval = 0.15  # ~7 req/s

    # ─── Rate Limiting ───────────────────────────────────────────

    def _wait_rate_limit(self):
        """Соблюдаем лимит 7 req/s."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    # ─── Base Request ────────────────────────────────────────────

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Any = None,
        params: dict = None,
        retries: int = 3,
    ) -> Optional[requests.Response]:
        """Универсальный запрос с retry и rate limiting."""
        url = f"{self.base_url}/{endpoint}"

        for attempt in range(retries):
            self._wait_rate_limit()
            try:
                r = requests.request(
                    method,
                    url,
                    headers=self.headers,
                    json=data,
                    params=params,
                    timeout=30,
                )

                if r.status_code == 429:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"Rate limited (429). Waiting {wait}s...")
                    time.sleep(wait)
                    continue

                if r.status_code >= 500:
                    logger.warning(
                        f"Server error {r.status_code}. Retry {attempt+1}/{retries}"
                    )
                    time.sleep(3)
                    continue

                return r

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout (attempt {attempt+1}/{retries})")
                time.sleep(5)
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error (attempt {attempt+1}/{retries})")
                time.sleep(10)

        logger.error(f"All {retries} attempts failed for {method} {endpoint}")
        return None

    # ─── Leads (Сделки) ──────────────────────────────────────────

    def get_leads(
        self,
        pipeline_id: int = None,
        status_id: int = None,
        limit: int = 250,
        page: int = 1,
        with_fields: bool = True,
    ) -> list[dict]:
        """Получить список сделок с фильтрацией."""
        params = {"limit": limit, "page": page}
        if with_fields:
            params["with"] = "custom_fields_values"
        if pipeline_id:
            params["filter[pipeline_id]"] = pipeline_id
        if status_id:
            params["filter[statuses][0][pipeline_id]"] = pipeline_id
            params["filter[statuses][0][status_id]"] = status_id

        r = self._request("GET", "leads", params=params)
        if r and r.status_code == 200:
            return r.json().get("_embedded", {}).get("leads", [])
        if r and r.status_code == 204:
            return []  # Нет данных
        return []

    def get_all_leads_in_status(
        self, pipeline_id: int, status_id: int
    ) -> list[dict]:
        """Получить ВСЕ сделки в определённом статусе (пагинация)."""
        all_leads = []
        page = 1
        while True:
            leads = self.get_leads(
                pipeline_id=pipeline_id,
                status_id=status_id,
                page=page,
            )
            if not leads:
                break
            all_leads.extend(leads)
            if len(leads) < 250:
                break
            page += 1
        return all_leads

    def get_lead(self, lead_id: int) -> Optional[dict]:
        """Получить одну сделку по ID."""
        r = self._request("GET", f"leads/{lead_id}", params={"with": "custom_fields_values"})
        if r and r.status_code == 200:
            return r.json()
        return None

    def create_lead(self, lead_data: dict) -> Optional[dict]:
        """Создать сделку."""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Создание сделки: {lead_data.get('name', '?')}")
            return {"id": 0, "_dry_run": True}

        r = self._request("POST", "leads", data=[lead_data])
        if r and r.status_code == 200:
            leads = r.json().get("_embedded", {}).get("leads", [])
            return leads[0] if leads else None
        logger.error(f"Ошибка создания сделки: {r.status_code if r else 'NO_RESPONSE'}")
        return None

    def update_lead(self, lead_id: int, update_data: dict) -> bool:
        """Обновить сделку (PATCH)."""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Обновление сделки {lead_id}: {update_data}")
            return True

        update_data["id"] = lead_id
        r = self._request("PATCH", "leads", data=[update_data])
        if r and r.status_code == 200:
            return True
        logger.error(
            f"Ошибка обновления сделки {lead_id}: "
            f"{r.status_code if r else 'NO_RESPONSE'} "
            f"{r.text[:200] if r else ''}"
        )
        return False

    def move_lead(
        self, lead_id: int, pipeline_id: int, status_id: int
    ) -> bool:
        """Перенести сделку в другую воронку/статус."""
        return self.update_lead(
            lead_id,
            {"pipeline_id": pipeline_id, "status_id": status_id},
        )

    # ─── Tasks (Задачи) ──────────────────────────────────────────

    def create_task(
        self,
        lead_id: int,
        text: str,
        responsible_user_id: int,
        deadline_seconds: int,
        task_type_id: int = 1,  # 1 = Звонок, 2 = Встреча, 3 = Написать
    ) -> Optional[dict]:
        """
        Создать задачу привязанную к сделке.
        
        deadline_seconds: через сколько секунд от текущего момента дедлайн.
        """
        complete_till = int(time.time()) + deadline_seconds

        task_data = {
            "text": text,
            "complete_till": complete_till,
            "responsible_user_id": responsible_user_id,
            "task_type_id": task_type_id,
            "entity_id": lead_id,
            "entity_type": "leads",
        }

        if self.dry_run:
            logger.info(
                f"[DRY-RUN] Задача для сделки {lead_id}: "
                f"'{text}' → user {responsible_user_id}, "
                f"дедлайн через {deadline_seconds//3600}ч"
            )
            return {"id": 0, "_dry_run": True}

        r = self._request("POST", "tasks", data=[task_data])
        if r and r.status_code == 200:
            tasks = r.json().get("_embedded", {}).get("tasks", [])
            return tasks[0] if tasks else None
        logger.error(
            f"Ошибка создания задачи: {r.status_code if r else 'NO_RESPONSE'}"
        )
        return None

    def create_task_at_date(
        self,
        lead_id: int,
        text: str,
        responsible_user_id: int,
        deadline_date: datetime,
        task_type_id: int = 1,
    ) -> Optional[dict]:
        """Создать задачу с абсолютной датой дедлайна."""
        complete_till = int(deadline_date.timestamp())

        task_data = {
            "text": text,
            "complete_till": complete_till,
            "responsible_user_id": responsible_user_id,
            "task_type_id": task_type_id,
            "entity_id": lead_id,
            "entity_type": "leads",
        }

        if self.dry_run:
            logger.info(
                f"[DRY-RUN] Задача для сделки {lead_id}: "
                f"'{text}' → user {responsible_user_id}, "
                f"дедлайн {deadline_date.isoformat()}"
            )
            return {"id": 0, "_dry_run": True}

        r = self._request("POST", "tasks", data=[task_data])
        if r and r.status_code == 200:
            tasks = r.json().get("_embedded", {}).get("tasks", [])
            return tasks[0] if tasks else None
        return None

    def get_tasks_for_lead(self, lead_id: int) -> list[dict]:
        """Получить все задачи для сделки."""
        params = {
            "filter[entity_id]": lead_id,
            "filter[entity_type]": "leads",
        }
        r = self._request("GET", "tasks", params=params)
        if r and r.status_code == 200:
            return r.json().get("_embedded", {}).get("tasks", [])
        return []

    def get_overdue_tasks(self) -> list[dict]:
        """Получить просроченные задачи."""
        params = {
            "filter[is_completed]": 0,
            "order[complete_till]": "asc",
        }
        r = self._request("GET", "tasks", params=params)
        if r and r.status_code == 200:
            tasks = r.json().get("_embedded", {}).get("tasks", [])
            now = int(time.time())
            return [t for t in tasks if t.get("complete_till", 0) < now]
        return []

    # ─── Notes (Примечания) ──────────────────────────────────────

    def add_note(
        self,
        lead_id: int,
        text: str,
        note_type: str = "common",
    ) -> Optional[dict]:
        """
        Добавить примечание к сделке.
        
        note_type: common, call_in, call_out, service_message
        """
        note_data = {
            "note_type": note_type,
            "params": {"text": text},
        }

        if self.dry_run:
            logger.info(f"[DRY-RUN] Примечание к сделке {lead_id}: '{text[:80]}...'")
            return {"id": 0, "_dry_run": True}

        r = self._request("POST", f"leads/{lead_id}/notes", data=[note_data])
        if r and r.status_code == 200:
            notes = r.json().get("_embedded", {}).get("notes", [])
            return notes[0] if notes else None
        logger.error(
            f"Ошибка добавления примечания: {r.status_code if r else 'NO_RESPONSE'}"
        )
        return None

    # ─── Custom Fields Helpers ───────────────────────────────────

    @staticmethod
    def get_custom_field_value(lead: dict, field_id: int) -> Optional[str]:
        """Извлечь значение кастомного поля из сделки."""
        fields = lead.get("custom_fields_values") or []
        for f in fields:
            if f["field_id"] == field_id:
                values = f.get("values", [])
                if values:
                    return values[0].get("value")
        return None

    @staticmethod
    def build_custom_fields_payload(fields_map: dict) -> list[dict]:
        """
        Построить payload для обновления кастомных полей.
        
        fields_map: {field_id: value, ...}
        """
        result = []
        for field_id, value in fields_map.items():
            if value is not None:
                result.append({
                    "field_id": field_id,
                    "values": [{"value": value}],
                })
        return result

    # ─── Users ───────────────────────────────────────────────────

    def get_users(self) -> list[dict]:
        """Получить список пользователей аккаунта."""
        r = self._request("GET", "users")
        if r and r.status_code == 200:
            return r.json().get("_embedded", {}).get("users", [])
        return []

    # ─── Pipelines & Statuses ────────────────────────────────────

    def get_pipelines(self) -> list[dict]:
        """Получить все воронки с их статусами."""
        r = self._request("GET", "leads/pipelines")
        if r and r.status_code == 200:
            return r.json().get("_embedded", {}).get("pipelines", [])
        return []

    # ─── Webhooks ────────────────────────────────────────────────

    def subscribe_webhook(self, url: str, events: list[str]) -> Optional[dict]:
        """
        Подписаться на вебхук.
        
        events: ["add_lead", "update_lead", "status_lead", ...]
        """
        if self.dry_run:
            logger.info(f"[DRY-RUN] Подписка на вебхук: {url} → {events}")
            return {"id": 0, "_dry_run": True}

        # amoCRM webhook subscription via API
        # Note: webhooks can also be configured in integration settings
        payload = {"destination": url, "settings": events}
        r = self._request("POST", "webhooks", data=payload)
        if r and r.status_code in (200, 201):
            return r.json()
        logger.error(
            f"Ошибка подписки на вебхук: {r.status_code if r else 'NO_RESPONSE'}"
        )
        return None

    def list_webhooks(self) -> list[dict]:
        """Получить список активных вебхуков."""
        r = self._request("GET", "webhooks")
        if r and r.status_code == 200:
            return r.json().get("_embedded", {}).get("webhooks", [])
        return []
