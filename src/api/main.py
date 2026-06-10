"""
FastAPI application entry point.
"""

import os
import logging
from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from src.api.routes import router
from src.application.cron_service import CronService
from src.api.dependencies import get_amo_client

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализация
load_dotenv()
app = FastAPI(title="RETEK amoCRM Microservice")
app.include_router(router)

# Планировщик
scheduler = BackgroundScheduler()

def run_hourly_cron():
    """Обертка для запуска cron-задачи."""
    try:
        amo_client = get_amo_client()
        service = CronService(amo_client)
        service.check_deadlines_and_escalate()
    except Exception as e:
        logger.error(f"Cron error: {e}")

@app.on_event("startup")
def startup_event():
    logger.info("Starting RETEK microservice v2 (Clean Architecture)")
    
    # Настройка cron-задач
    scheduler.add_job(run_hourly_cron, 'cron', minute=5)
    scheduler.start()
    logger.info("Scheduler started. Hourly cron scheduled at :05")

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()
    logger.info("Scheduler shut down.")
