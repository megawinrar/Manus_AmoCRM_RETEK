"""
FastAPI dependencies for DI.
"""

import os
from src.infrastructure.amocrm_client import AmoClient
from src.infrastructure.yadisk_client import YaDiskClient

def get_amo_client() -> AmoClient:
    subdomain = os.getenv("AMO_SUBDOMAIN", "")
    token = os.getenv("AMO_ACCESS_TOKEN", "")
    return AmoClient(subdomain, token)

def get_yadisk_client() -> YaDiskClient:
    token = os.getenv("YADISK_TOKEN", "")
    return YaDiskClient(token)
