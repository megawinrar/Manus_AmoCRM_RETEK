# AGENTS.md — Правила работы с проектом RETEK amoCRM

## Критические правила

### 1. НЕ СПАМИТЬ API amoCRM
- **Никогда** не делать лишних проверочных/тестовых запросов к amoCRM API
- Не вызывать GET /leads, GET /account и т.д. просто "чтобы проверить что токен работает"
- Не создавать тестовые сделки/примечания без крайней необходимости
- Объединять операции: один PATCH вместо нескольких
- Rate limit amoCRM: 7 req/s — превышение ведёт к бану аккаунта
- Если нужно проверить работоспособность — использовать только `/health` endpoint нашего сервиса

### 2. Не удалять сделки из amoCRM
- Только обогащать существующие сделки новой информацией

### 3. Коммиты
- Все изменения коммитить с номером патча (PATCH16, PATCH17, ...)
- SESSION_STATE.md обновлять после каждого патча

### 4. Код
- Старый код в `src/microservice/` сохранять (VM работает на нём)
- Новая Clean Architecture в `src/domain/`, `src/application/`, `src/infrastructure/`, `src/api/`
- DRY_RUN=0 на production, LLM_MODE=training

### 5. Деплой
- VM: 89.169.142.160, user: yc-user, path: /opt/Manus_AmoCRM_RETEK
- Docker: `docker compose -f deploy/docker-compose.yml up -d --build app`
- После деплоя проверять только `curl http://localhost:8000/health`

### 6. Тестирование и покрытие
- Все изменения оборачивать тестами перед коммитом
- Текущее покрытие: **55%** (417 тестов), цель: >70%
- Для улучшения покрытия использовать скилл **test-coverage-improver**
  - Репозиторий: https://github.com/megawinrar/manus-skills/tree/main/test-coverage-improver
  - Workflow: baseline → приоритизация модулей → написание тестов → фикс багов → коммит
- Запуск тестов: `python -m pytest tests/ --cov=src --cov-report=term-missing --tb=short -q`
- Не тестировать одноразовые скрипты (`src/create_custom_fields.py`, `src/rebuild_statuses.py` и т.д.)
- Фокус на: API layer, cron jobs, handlers, services, infrastructure clients

## Навыки (Skills)

| Навык | Описание | Репозиторий |
| :--- | :--- | :--- |
| test-coverage-improver | Анализ покрытия, написание тестов, исправление багов, коммит в GitHub | [manus-skills](https://github.com/megawinrar/manus-skills/tree/main/test-coverage-improver) |
