"""
RETEK amoCRM Microservice — точка входа.

Запуск:
    uvicorn src.microservice.main:app --host 0.0.0.0 --port 8000

Или с dry-run:
    DRY_RUN=1 uvicorn src.microservice.main:app --host 0.0.0.0 --port 8000

Компоненты:
- FastAPI — обработка вебхуков amoCRM
- APScheduler — периодические задачи (hourly, daily, weekly, monthly)
- Logging — структурированное логирование
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .webhook_handler import router as webhook_router
from .cron_hourly import run_hourly
from .cron_daily import run_daily
from .cron_weekly import run_weekly
from .cron_monthly import run_monthly
from .cron_yadisk import run_yadisk_scan

# ═══════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("microservice.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# DRY-RUN MODE
# ═══════════════════════════════════════════════════════════════════

DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
if DRY_RUN:
    logger.warning("⚠️ DRY-RUN MODE — никакие действия НЕ применяются к amoCRM")

# ═══════════════════════════════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════════════════════════════

scheduler = AsyncIOScheduler()


def _job_hourly():
    """Обёртка для ежечасного задания."""
    logger.info("⏰ Запуск ежечасного контроля...")
    try:
        stats = run_hourly(dry_run=DRY_RUN)
        logger.info(f"⏰ Ежечасный контроль завершён: {stats}")
    except Exception as e:
        logger.error(f"⏰ Ошибка ежечасного контроля: {e}", exc_info=True)


def _job_daily():
    """Обёртка для ежедневного задания."""
    logger.info("📦 Запуск ежедневной архивации...")
    try:
        stats = run_daily(dry_run=DRY_RUN)
        logger.info(f"📦 Ежедневная архивация завершена: {stats}")
    except Exception as e:
        logger.error(f"📦 Ошибка ежедневной архивации: {e}", exc_info=True)


def _job_weekly():
    """Обёртка для еженедельного задания."""
    logger.info("📋 Запуск еженедельного контроля...")
    try:
        stats = run_weekly(dry_run=DRY_RUN)
        logger.info(f"📋 Еженедельный контроль завершён: {stats}")
    except Exception as e:
        logger.error(f"📋 Ошибка еженедельного контроля: {e}", exc_info=True)


def _job_yadisk_scan():
    """Обёртка для сканирования Яндекс.Диска."""
    logger.info("📂 Запуск сканирования Яндекс.Диска...")
    try:
        stats = run_yadisk_scan(dry_run=DRY_RUN)
        logger.info(f"📂 Сканирование завершено: {stats.get('new_tenders', 0)} новых")
    except Exception as e:
        logger.error(f"📂 Ошибка сканирования Яндекс.Диска: {e}", exc_info=True)


def _job_monthly():
    """Обёртка для ежемесячного задания."""
    logger.info("📊 Запуск ежемесячной ревизии...")
    try:
        report = run_monthly(dry_run=DRY_RUN)
        logger.info(f"📊 Ежемесячная ревизия завершена")
    except Exception as e:
        logger.error(f"📊 Ошибка ежемесячной ревизии: {e}", exc_info=True)


def setup_scheduler():
    """Настройка расписания задач."""
    # Каждый час (в :05 минут чтобы не совпадать с другими процессами)
    scheduler.add_job(
        _job_hourly,
        CronTrigger(minute=5),
        id="hourly_control",
        name="Ежечасный контроль Р1/Р2",
        replace_existing=True,
    )

    # Каждый день в 02:00 (ночью, когда нет нагрузки)
    scheduler.add_job(
        _job_daily,
        CronTrigger(hour=2, minute=0),
        id="daily_archive",
        name="Ежедневная архивация",
        replace_existing=True,
    )

    # Каждый понедельник в 09:00
    scheduler.add_job(
        _job_weekly,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="weekly_control",
        name="Еженедельный контроль зависших",
        replace_existing=True,
    )

    # Каждый час в :30 — сканирование Яндекс.Диска
    scheduler.add_job(
        _job_yadisk_scan,
        CronTrigger(minute=30),
        id="yadisk_scan",
        name="Сканирование Яндекс.Диска (новые тендеры)",
        replace_existing=True,
    )

    # 1-го числа каждого месяца в 10:00
    scheduler.add_job(
        _job_monthly,
        CronTrigger(day=1, hour=10, minute=0),
        id="monthly_revision",
        name="Ежемесячная ревизия архива",
        replace_existing=True,
    )

    logger.info("📅 Планировщик настроен:")
    logger.info("  • Ежечасно — :05 каждого часа (контроль Р1/Р2)")
    logger.info("  • Ежечасно — :30 каждого часа (сканирование Яндекс.Диска)")
    logger.info("  • Ежедневно — 02:00 (архивация)")
    logger.info("  • Еженедельно — понедельник 09:00")
    logger.info("  • Ежемесячно — 1-е число 10:00")


# ═══════════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle: запуск и остановка планировщика."""
    setup_scheduler()
    scheduler.start()
    logger.info("🚀 RETEK Microservice запущен")
    logger.info(f"   Mode: {'DRY-RUN' if DRY_RUN else 'PRODUCTION'}")
    logger.info(f"   Time: {datetime.now().isoformat()}")
    yield
    scheduler.shutdown()
    logger.info("🛑 RETEK Microservice остановлен")


app = FastAPI(
    title="RETEK amoCRM Microservice",
    description=(
        "Внешний микросервис для автоматизации тендерного процесса RETEK.\n"
        "Обрабатывает вебхуки amoCRM и выполняет периодические задачи."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Подключаем роутер вебхуков
app.include_router(webhook_router, tags=["webhooks"])


# ═══════════════════════════════════════════════════════════════════
# ДОПОЛНИТЕЛЬНЫЕ ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    """Корневой endpoint — информация о сервисе."""
    return {
        "service": "RETEK amoCRM Microservice",
        "version": "1.1.0",
        "mode": "dry-run" if DRY_RUN else "production",
        "endpoints": {
            "webhook": "POST /webhook",
            "health": "GET /health",
            "status": "GET /status",
            "run_hourly": "POST /run/hourly",
            "run_daily": "POST /run/daily",
            "run_weekly": "POST /run/weekly",
            "run_monthly": "POST /run/monthly",
            "run_yadisk": "POST /run/yadisk",
        },
    }


@app.get("/status")
async def service_status():
    """Статус сервиса и планировщика."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
        })

    return {
        "status": "running",
        "mode": "dry-run" if DRY_RUN else "production",
        "scheduler_running": scheduler.running,
        "jobs": jobs,
        "timestamp": datetime.now().isoformat(),
    }


# ─── Ручной запуск задач (для тестирования) ──────────────────────

@app.post("/run/hourly")
async def manual_run_hourly():
    """Ручной запуск ежечасного контроля."""
    stats = run_hourly(dry_run=DRY_RUN)
    return {"status": "completed", "stats": stats}


@app.post("/run/daily")
async def manual_run_daily():
    """Ручной запуск ежедневной архивации."""
    stats = run_daily(dry_run=DRY_RUN)
    return {"status": "completed", "stats": stats}


@app.post("/run/weekly")
async def manual_run_weekly():
    """Ручной запуск еженедельного контроля."""
    stats = run_weekly(dry_run=DRY_RUN)
    return {"status": "completed", "stats": stats}


@app.post("/run/monthly")
async def manual_run_monthly():
    """Ручной запуск ежемесячной ревизии."""
    report = run_monthly(dry_run=DRY_RUN)
    return {"status": "completed", "report_date": report.get("date")}


@app.post("/run/yadisk")
async def manual_run_yadisk():
    """Ручной запуск сканирования Яндекс.Диска."""
    stats = run_yadisk_scan(dry_run=DRY_RUN)
    return {"status": "completed", "stats": stats}


# ═══════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
