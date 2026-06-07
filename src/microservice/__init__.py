"""
RETEK amoCRM Microservice — пакет автоматизации тендерного процесса.

Модули:
- amo_client: HTTP-клиент amoCRM API v4
- config: конфигурация, правила маршрутизации, ID полей/статусов
- webhook_handler: обработка вебхуков (FastAPI router)
- cron_hourly: ежечасный контроль приоритетов
- cron_daily: ежедневная архивация
- cron_weekly: еженедельный контроль зависших
- cron_monthly: ежемесячная ревизия архива
- main: точка входа (FastAPI + APScheduler)
"""
