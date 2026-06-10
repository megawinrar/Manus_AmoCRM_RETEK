# FAQ-Pipeline: Быстрый старт для новой сессии

> **Цель этого документа**: В новой сессии ты (AI-агент) должен прочитать этот файл ПЕРВЫМ,
> чтобы понять что где лежит и как работает система. НЕ создавай ничего нового —
> используй то, что уже есть.

---

## Быстрые ответы

### Где проект на сервере?
```
Сервер: 89.169.142.160 (Яндекс Клауд)
SSH: ssh -i ~/.ssh/yc_key yc-user@89.169.142.160
Проект на хосте: /opt/Manus_AmoCRM_RETEK/
Проект в Docker: /app/ (контейнер retek-amocrm)
```

### Как подключиться к серверу?
```bash
ssh -o StrictHostKeyChecking=no -i ~/.ssh/yc_key yc-user@89.169.142.160
```

### Как посмотреть логи?
```bash
sudo docker logs retek-amocrm --tail 100
sudo docker logs retek-amocrm --since 1h
sudo docker logs retek-amocrm -f  # live
```

### Как перезапустить сервис?
```bash
cd /opt/Manus_AmoCRM_RETEK
sudo docker compose -f deploy/docker-compose.yml restart app
```

### Как пересобрать и задеплоить?
```bash
cd /opt/Manus_AmoCRM_RETEK
git pull origin main  # или нужную ветку
sudo docker compose -f deploy/docker-compose.yml build app
sudo docker compose -f deploy/docker-compose.yml up -d app
```

### Как проверить что сервис работает?
```bash
curl -s http://localhost:8000/health
# Ответ: {"status":"ok","service":"RETEK amoCRM Microservice","timestamp":"..."}
```

### Как запустить сканирование вручную?
```bash
curl -s -X POST http://localhost:8000/run/yadisk
```

### Как выполнить команду внутри контейнера?
```bash
sudo docker exec retek-amocrm python3 -c "print('hello')"
sudo docker exec -it retek-amocrm bash
```

---

## Структура Docker-контейнера `retek-amocrm`

```
/app/                              ← WORKDIR
├── src/microservice/              ← Основной сервис
│   ├── main.py                   ← Точка входа (uvicorn)
│   ├── cron_yadisk.py            ← ⭐ Главный pipeline
│   ├── cron_hourly.py            ← Ежечасный контроль
│   ├── amo_client.py             ← API клиент amoCRM
│   ├── webhook_handler.py        ← Вебхуки
│   ├── action3_handler.py        ← Действие 3
│   ├── deduplication.py          ← Дедупликация
│   ├── field_validator.py        ← Валидация
│   └── config.py                 ← Конфигурация
├── scripts/
│   ├── chunk_score_extractor.py  ← ⭐ Модуль распознавания (чанки + баллы)
│   ├── extract_and_classify.py   ← Legacy парсер
│   └── ...
├── docs/                          ← Документация
├── data/                          ← Docker volume (персистентные данные)
│   ├── processed_tenders.db      ← SQLite: обработанные тендеры
│   └── dedup.db                  ← SQLite: дедупликация
├── logs/                          ← Docker volume (логи)
└── backups/                       ← Docker volume (бэкапы)
```

### Важно: Docker volumes
Данные в `/app/data/`, `/app/logs/`, `/app/backups/` — это **Docker volumes**.
Они **сохраняются** при пересборке контейнера.
На хосте: `sudo docker volume inspect deploy_app-data`

---

## Как работает система (Pipeline)

### 1. Запуск
```
Docker daemon (systemd) → контейнер retek-amocrm (restart: always)
→ uvicorn src.microservice.main:app (2 workers)
→ APScheduler запускает cron jobs
```

### 2. Сканирование Яндекс.Диска (каждые 5 минут)
```
cron_yadisk.run_yadisk_scan()
  → scan_root_folder() — листинг /ТОРГИ/DD.MM.YYYY/
  → Для каждой папки-тендера:
    → is_tender_processed() — проверка SQLite
    → download files (PDF, DOCX, XLSX)
    → TenderDeduplicator.check() — дедупликация
    → chunk_score_extractor.parse_tender_folder() — распознавание
    → amo_client.create_lead() — создание сделки
    → mark_tender_processed() — запись в SQLite
```

### 3. Распознавание (chunk_score_extractor.py)
```
parse_tender_folder(file_paths)
  → extract_file_text() — извлечение текста (pdftotext / python-docx / openpyxl)
  → split_into_chunks() — разбиение на чанки (250 токенов, overlap 50)
  → score_chunk_for_field() — балльная оценка чанков для каждого поля
  → extract_*() — regex-извлечение из лучших чанков
  → apply_ocr_fallback() — OCR если confidence < 0.5
  → score_direction() — определение направления (CARBIDE/HSS/DIAMOND/...)
  → determine_priority() — приоритет (Р1/Р2/Р3)
```

### 4. Вебхуки (webhook_handler.py)
```
POST /webhook ← amoCRM
  → handle_status_change() — смена статуса сделки
  → handle_lead_add() — новая сделка
  → handle_note_add() → action3_handler — Действие 3 (note с ссылкой на YaDisk)
```

---

## Конфигурация (.env)

| Переменная | Описание |
|-----------|----------|
| `AMO_SUBDOMAIN` | Поддомен amoCRM (retektools) |
| `AMO_CLIENT_ID` | OAuth client ID |
| `AMO_CLIENT_SECRET` | OAuth client secret |
| `AMO_ACCESS_TOKEN` | Access token |
| `AMO_REFRESH_TOKEN` | Refresh token |
| `YADISK_TOKEN` | Токен Яндекс.Диска |
| `YADISK_ROOT_FOLDER` | Корневая папка (/ТОРГИ) |
| `DRY_RUN` | 0 = production, 1 = без записи в amoCRM |
| `LLM_MODE` | production / training |
| `YANDEX_GPT_API_KEY` | Ключ YandexGPT |
| `YANDEX_GPT_FOLDER_ID` | Folder ID YandexGPT |

---

## Частые проблемы и решения

### Тендеры помечаются как duplicate
```bash
# Очистить базу дедупликации
sudo docker exec retek-amocrm rm -f /app/data/dedup.db
sudo docker compose -f deploy/docker-compose.yml restart app
```

### OCR не работает
```bash
# Проверить зависимости внутри контейнера
sudo docker exec retek-amocrm python3 -c "import pytesseract; import pdf2image; print('OK')"
sudo docker exec retek-amocrm tesseract --list-langs
```

### Сервис не отвечает
```bash
sudo docker ps | grep retek
sudo docker logs retek-amocrm --tail 20
sudo docker compose -f deploy/docker-compose.yml restart app
```

### Нужно обновить код без пересборки (быстро)
```bash
# Скопировать файл в работающий контейнер (НЕ переживёт пересборку!)
sudo docker cp /opt/Manus_AmoCRM_RETEK/scripts/chunk_score_extractor.py retek-amocrm:/app/scripts/
sudo docker restart retek-amocrm
```

### Нужно обновить код с пересборкой (правильно)
```bash
cd /opt/Manus_AmoCRM_RETEK
git pull origin main
sudo docker compose -f deploy/docker-compose.yml build app
sudo docker compose -f deploy/docker-compose.yml up -d app
```

---

## Правила для AI-агента

1. **ВСЕГДА читай этот файл первым** в новой сессии
2. **НЕ создавай новые файлы/структуры** без необходимости — используй существующие
3. **Проект в Docker** — изменения на хосте НЕ попадают в контейнер автоматически
4. **Для деплоя**: git pull → docker build → docker up
5. **Для быстрого теста**: docker cp → docker restart (но это временно!)
6. **Тесты обязательны** для каждого изменения
7. **Отдельная ветка** для глобальных изменений: `feature/описание_YYYY-MM-DD_HHMM`
8. **Cron каждые 5 минут** — не менять без согласования
9. **Не спамить amoCRM** — проверяй дедупликацию
10. **Логи** — всегда проверяй `docker logs` после изменений

---

## GitHub репозиторий

```
https://github.com/megawinrar/Manus_AmoCRM_RETEK
Ветка main — стабильная production
Ветки feature/* — новые фичи с датой
```

---

*Последнее обновление: 2026-06-10*
