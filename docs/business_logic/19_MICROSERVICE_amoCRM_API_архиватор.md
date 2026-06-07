# Микросервис amoCRM: создание сделок, маршрутизация, архиватор

## Назначение

Микросервис связывает LLM и amoCRM.

## Основные функции

```text
создать сделку из JSON LLM
обновить сделку
создать задачу
добавить примечание
перенести сделку в другой статус
перенести сделку в архивную воронку
проверить просрочки
создать задачу на дату возврата
```

## Процесс создания сделки

```text
LLM JSON
→ validate required fields
→ find/create customer/contact if needed
→ create lead in active pipeline
→ set status by routing
→ set responsible by routing
→ add note with LLM summary
→ create task for next action
```

## Процесс архивирования

```text
cron daily
→ get leads in status "К архивированию"
→ validate archive fields
→ choose archive pipeline/status
→ update lead pipeline_id/status_id
→ add note
→ create future task if return date exists
```

## Процесс контроля

```text
cron hourly
→ find overdue Р1/Р2
→ find leads with no next action
→ find leads stuck in one status too long
→ create task / notify responsible
```

## Ошибки

Если поля неполные:

```text
do not archive
add note: "Не хватает данных для архивирования"
create task for responsible
```

## Поля, которые нельзя доверять только LLM

```text
Итоговое архивное назначение
Причина закрытия
Решение дилера
Фактический результат торгов
```

LLM может предложить, но человек подтверждает.
