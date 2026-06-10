"""
LLM adapter (Yandex GPT).
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

class YandexGPTClient:
    def __init__(self, folder_id: str, api_key: str):
        self.folder_id = folder_id
        self.api_key = api_key
        self.base_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        self.headers = {
            "Authorization": f"Api-Key {api_key}",
            "x-folder-id": folder_id,
            "Content-Type": "application/json"
        }
        self.mode = os.getenv("LLM_MODE", "training")

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        """Отправить запрос к Yandex GPT."""
        
        # Если training mode, не тратим квоту, возвращаем заглушку
        if self.mode == "training":
            logger.info("[LLM_MODE=training] Skipping real Yandex GPT call.")
            return '{"direction": "HSS-06", "priority": "Р2", "situation_type": "СОЗ", "customer": "ООО Завод"}'
            
        payload = {
            "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite/latest",
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": 1000
            },
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_prompt}
            ]
        }
        
        try:
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data["result"]["alternatives"][0]["message"]["text"]
        except Exception as e:
            logger.error(f"Yandex GPT Error: {str(e)}")
            return ""
