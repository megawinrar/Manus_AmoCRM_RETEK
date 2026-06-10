# RETEK amoCRM — Refactoring Plan (Clean Architecture)

## Текущие проблемы

1. **Монолитный config.py (716 строк)** — смешаны: модели данных, бизнес-правила, шаблоны сообщений, маппинги enum
2. **Дублирование HTTP-клиентов** — `amo_client.py`, `field_validator.py`, `cron_backup.py` каждый делает свои requests
3. **Нет разделения слоёв** — бизнес-логика (эскалация, маршрутизация) живёт в тех же файлах что и HTTP-вызовы
4. **Hardcoded enum IDs** — `action3_handler.py` дублирует маппинги из config.py
5. **cron_yadisk.py (895 строк)** — сканирование, скачивание, дедупликация, классификация, создание карточки — всё в одном файле

## Новая структура (Clean Architecture)

```
src/
├── domain/                          # Ядро: модели, правила, интерфейсы (0 зависимостей)
│   ├── __init__.py
│   ├── models.py                    # Dataclasses: Tender, Lead, Priority, Direction, etc.
│   ├── enums.py                     # Все Enum: Priority, Direction, SituationType, CloseReason
│   ├── fields.py                    # Field IDs (из config.py Fields class)
│   ├── statuses.py                  # Pipeline/Status IDs (из config.py ActiveStatuses, Archive*)
│   ├── users.py                     # User IDs
│   ├── routing_rules.py            # resolve_routing, ROUTING_RULES, ARCHIVE_ROUTING
│   ├── escalation_rules.py         # auto_escalate_priority, ESCALATION thresholds
│   ├── task_rules.py               # STATUS_TASK_RULES, get_status_task_rules
│   ├── validation_rules.py         # ARCHIVE_REQUIRED_FIELDS, field validation policies
│   ├── note_templates.py           # STATUS_NOTE_TEMPLATES, ESCALATION_NOTE_TEMPLATE
│   └── naming.py                   # build_lead_name, PRIORITY_LABELS, PRIORITY_TAG_IDS
│
├── application/                     # Use Cases: оркестрация (зависит только от domain)
│   ├── __init__.py
│   ├── ports.py                     # ABC интерфейсы: ICrmGateway, IDiskStorage, ILlmService, IDatabase
│   ├── webhook_service.py          # handle_status_change, handle_lead_add, handle_note_add
│   ├── action3_service.py          # process_action3 (ссылка → скачать → распознать → заполнить)
│   ├── hourly_service.py           # escalate_by_deadline, control_priority_leads
│   ├── daily_service.py            # archive_leads, check_return_dates
│   ├── weekly_service.py           # find_stuck_leads
│   ├── monthly_service.py          # generate_monthly_report
│   ├── yadisk_service.py           # scan_and_process_new_tenders
│   ├── classification_service.py   # extract_and_classify orchestration
│   ├── deduplication_service.py    # check_duplicates, enrich_existing
│   └── backup_service.py           # create_backup, upload_to_disk
│
├── infrastructure/                  # Адаптеры: реализации портов (внешние зависимости)
│   ├── __init__.py
│   ├── amocrm/
│   │   ├── __init__.py
│   │   ├── client.py               # AmoClient (единственный HTTP-клиент для amoCRM)
│   │   └── mapper.py               # Маппинг domain models ↔ amoCRM JSON payloads
│   ├── yadisk/
│   │   ├── __init__.py
│   │   ├── client.py               # YaDiskClient (OAuth + public API)
│   │   └── scanner.py              # Логика сканирования папок /ТОРГИ
│   ├── llm/
│   │   ├── __init__.py
│   │   └── yandex_gpt.py           # YandexGPT adapter (implements ILlmService)
│   ├── ocr/
│   │   ├── __init__.py
│   │   └── extractor.py            # PDF/DOCX/XLSX text extraction + OCR
│   ├── database/
│   │   ├── __init__.py
│   │   ├── sqlite_repo.py          # SQLite: dedup DB, processed tenders, snapshots
│   │   └── migrations.py           # Schema init
│   └── auth/
│       ├── __init__.py
│       └── oauth.py                 # amoCRM OAuth token management
│
├── api/                             # Точка входа: FastAPI + Scheduler (тонкий слой)
│   ├── __init__.py
│   ├── app.py                       # FastAPI app creation, lifespan, include routers
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── webhook.py               # POST /webhook → вызывает webhook_service
│   │   ├── health.py                # GET /health, GET /status
│   │   └── manual.py                # POST /run/hourly, /run/daily, etc.
│   ├── scheduler.py                 # APScheduler setup (вызывает application services)
│   └── dependencies.py              # DI: создание клиентов, injection в routes
│
└── main.py                          # uvicorn entrypoint (создаёт app из api/)
```

## Принципы

1. **Domain** — чистый Python, никаких import requests/sqlite3/fastapi. Только dataclasses, enums, чистые функции.
2. **Application** — оркестрация через порты (ABC). Не знает про HTTP, SQL, конкретные API.
3. **Infrastructure** — реализует порты. Знает про requests, sqlite3, yandex API.
4. **API** — тонкая прослойка: парсит HTTP → вызывает application → возвращает JSON.
5. **Dependency Injection** — в `dependencies.py` создаём конкретные адаптеры и передаём в services.

## Порядок миграции

1. Создать `domain/` — вынести из config.py все модели, enum, правила
2. Создать `application/ports.py` — определить интерфейсы
3. Создать `infrastructure/` — перенести AmoClient, YaDiskClient, LLM, SQLite
4. Создать `application/` services — перенести бизнес-логику из cron_*, webhook_handler
5. Создать `api/` — тонкие routes + scheduler + DI
6. Обновить тесты, Dockerfile, requirements
7. Проверить: lint + tests + Docker build
