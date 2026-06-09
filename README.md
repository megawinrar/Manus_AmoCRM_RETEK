# RETEK amoCRM Integration

Микросервис автоматизации тендерного процесса компании RETEK. Интегрирует amoCRM, Яндекс.Диск и Яндекс GPT в единую систему обработки тендеров.

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    RETEK Microservice v1.1                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  📂 Яндекс.Диск (/ТОРГИ)                                    │
│  │   опрос каждый час (:30)                                  │
│  │   рекурсивный обход папок                                 │
│  │   дедупликация через SQLite                               │
│  ▼                                                           │
│  🤖 LLM Классификатор (Яндекс GPT)                           │
│  │   Действие 1: Классификация тендера                       │
│  │   Действие 2: Архивное назначение (ночной cron)           │
│  │   Действие 3: Распознавание из чата (будущее)             │
│  ▼                                                           │
│  📋 amoCRM API                                               │
│  │   создание сделок, задач, заметок                         │
│  │   перенос в архивные воронки                               │
│  │   контроль просрочек и WIP-лимитов                        │
│  │                                                           │
│  ⏰ Расписание (APScheduler)                                  │
│  │   :05 — контроль Р1/Р2                                    │
│  │   :30 — сканирование Яндекс.Диска                        │
│  │   02:00 — архивация + LLM-назначение                      │
│  │   Пн 09:00 — зависшие карточки                            │
│  │   1-е число — ревизия архива                              │
│  │                                                           │
│  🔍 Дедупликация + Валидация                                 │
│  │   хеш-сравнение файлов (SHA-256)                          │
│  │   fuzzy-match заказчик + НМЦ                              │
│  │   обогащение карточки при новых файлах                     │
│  │   валидация обязательных полей по статусам                 │
│  │                                                           │
│  💾 Хранилище                                                │
│  │   SQLite: processed_tenders.db                            │
│  │   Логи LLM: data/llm_logs/                               │
│  │   .env: токены, ID статусов                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Структура репозитория

```
├── src/microservice/
│   ├── main.py              # FastAPI + APScheduler (точка входа)
│   ├── config.py            # Все правила, статусы, маршрутизация
│   ├── amo_client.py        # amoCRM API клиент (rate-limit, retry)
│   ├── webhook_handler.py   # Обработка вебхуков amoCRM
│   ├── cron_hourly.py       # Контроль Р1/Р2 и просрочек
│   ├── cron_yadisk.py       # Сканирование Яндекс.Диска
│   ├── cron_daily.py        # Архивация + LLM-назначение
│   ├── cron_weekly.py       # Зависшие карточки
│   ├── cron_monthly.py      # Ревизия архива
│   ├── llm_classifier.py   # Яндекс GPT классификатор
│   ├── deduplication.py     # Дедупликация + обогащение тендеров
│   └── field_validator.py   # Валидация обязательных полей по статусам
├── docs/
│   ├── CONTEXT_FULL.md      # Полный контекст проекта (RAG)
│   └── amocrm_fields_and_logic.md  # Поля и логика amoCRM
├── tests/
│   ├── test_microservice.py # 29 тестов (config, webhook, cron)
│   ├── test_deduplication.py # 35 тестов (дубли, обогащение, fuzzy)
│   └── test_amo_api.py      # 14 тестов (API клиент)
├── data/                    # SQLite + логи LLM (gitignored)
├── .env                     # Конфигурация (не в git)
├── SETUP.md                 # Инструкция по настройке
└── requirements.txt         # Зависимости Python
```

## Требования

- Python 3.10+
- Аккаунт amoCRM с внешней интеграцией
- Яндекс.Диск OAuth-приложение (cloud_api:disk.read)
- Яндекс Cloud API-ключ (для Яндекс GPT)

## Быстрый старт

```bash
# Клонирование
gh repo clone megawinrar/Manus_AmoCRM_RETEK
cd Manus_AmoCRM_RETEK

# Установка зависимостей
pip install -r requirements.txt

# Настройка (скопировать и заполнить .env)
cp .env.example .env

# Запуск в тестовом режиме
DRY_RUN=1 uvicorn src.microservice.main:app --host 0.0.0.0 --port 8000

# Тесты
pytest tests/ -v
```

## Режимы работы

| Переменная | Значение | Описание |
|---|---|---|
| `DRY_RUN` | `1` | Ничего не меняет в amoCRM (для тестирования) |
| `DRY_RUN` | `0` | Боевой режим |
| `LLM_MODE` | `training` | LLM работает, логирует, НЕ применяет |
| `LLM_MODE` | `production` | LLM применяет результаты автоматически |

## API Endpoints

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/` | Информация о сервисе |
| `GET` | `/health` | Проверка здоровья |
| `GET` | `/status` | Статус планировщика |
| `POST` | `/webhook` | Вебхук amoCRM |
| `POST` | `/run/hourly` | Ручной запуск контроля Р1/Р2 |
| `POST` | `/run/daily` | Ручной запуск архивации |
| `POST` | `/run/weekly` | Ручной запуск проверки зависших |
| `POST` | `/run/monthly` | Ручной запуск ревизии |
| `POST` | `/run/yadisk` | Ручной запуск сканирования Яндекс.Диска |

## Интеграции

- **amoCRM:** tokutools.amocrm.ru (внешняя интеграция, JWT до 29.07.2026)
- **Яндекс.Диск:** приложение ЯндексДиск_AmoCRM (OAuth, cloud_api:disk.read)
- **Яндекс GPT:** OpenAI-compatible API (https://ai.api.cloud.yandex.net/v1)

## Документация

- [SETUP.md](SETUP.md) — подробная инструкция по настройке и деплою
- [docs/CONTEXT_FULL.md](docs/CONTEXT_FULL.md) — полный контекст проекта (используется как RAG для LLM)
- [docs/amocrm_fields_and_logic.md](docs/amocrm_fields_and_logic.md) — поля и бизнес-логика amoCRM
