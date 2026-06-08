"""
Ежедневная архивация — cron_daily.

Задачи:
1. Забрать сделки из статуса «К архивированию»
2. Проверить обязательные поля
3. Если поля заполнены → перенести в архивную воронку + примечание + задача на возврат
4. Если поля НЕ заполнены → задача ответственному «Заполнить данные»
5. Проверить архивные сделки с наступившей «Датой возврата» → задача на возврат
"""

import logging
import time
from datetime import datetime, timedelta

from .amo_client import AmoClient
from .config import (
    PIPELINE_ACTIVE,
    PIPELINE_ARCHIVE_DIRECTIONS,
    PIPELINE_ARCHIVE_SOZ,
    ActiveStatuses,
    Fields,
    Users,
    ARCHIVE_REQUIRED_FIELDS,
    ARCHIVE_REQUIRED_FIELD_NAMES,
    resolve_archive_destination,
)

logger = logging.getLogger(__name__)


class DailyArchiver:
    """Ежедневный процесс архивации."""

    def __init__(self, dry_run: bool = False):
        self.client = AmoClient(dry_run=dry_run)
        self.dry_run = dry_run
        self.stats = {
            "found_to_archive": 0,
            "archived_ok": 0,
            "incomplete_fields": 0,
            "return_tasks_created": 0,
            "errors": 0,
        }

    def run(self):
        """Запуск ежедневной архивации."""
        logger.info("=" * 60)
        logger.info(f"[DAILY] Начало архивации — {datetime.now().isoformat()}")
        logger.info("=" * 60)

        try:
            self._archive_leads()
            self._check_return_dates()
        except Exception as e:
            logger.error(f"[DAILY] Критическая ошибка: {e}", exc_info=True)
            self.stats["errors"] += 1

        logger.info(f"[DAILY] Завершено. Статистика: {self.stats}")
        return self.stats

    # ─── 1. Архивация сделок ─────────────────────────────────────

    def _archive_leads(self):
        """Забрать сделки из 'К архивированию' и обработать."""
        logger.info("[DAILY] Получаю сделки из статуса 'К архивированию'...")

        if not ActiveStatuses.TO_ARCHIVE:
            logger.error("[DAILY] STATUS_11_ARCHIVE не настроен в .env!")
            return

        leads = self.client.get_all_leads_in_status(
            pipeline_id=PIPELINE_ACTIVE,
            status_id=ActiveStatuses.TO_ARCHIVE,
        )

        self.stats["found_to_archive"] = len(leads)
        logger.info(f"[DAILY] Найдено сделок к архивации: {len(leads)}")

        for lead in leads:
            self._process_lead_for_archive(lead)

    def _process_lead_for_archive(self, lead: dict):
        """Обработать одну сделку для архивации."""
        lead_id = lead["id"]
        lead_name = lead.get("name", "Без названия")

        logger.info(f"[DAILY] Обработка: {lead_id} — '{lead_name}'")

        # Шаг 1: Проверить обязательные поля
        missing_fields = self._validate_archive_fields(lead)

        if missing_fields:
            # Поля не заполнены — задача ответственному
            self.stats["incomplete_fields"] += 1
            self._handle_incomplete_lead(lead, missing_fields)
            return

        # Шаг 2: Определить целевую воронку/статус
        archive_dest = AmoClient.get_custom_field_value(
            lead, Fields.ARCHIVE_DEST_FINAL
        )

        if not archive_dest:
            # Fallback на LLM-назначение
            archive_dest = AmoClient.get_custom_field_value(
                lead, Fields.ARCHIVE_DEST_LLM
            )

        if not archive_dest:
            logger.warning(
                f"[DAILY] Сделка {lead_id}: нет архивного назначения!"
            )
            self._handle_incomplete_lead(
                lead, ["Архивное назначение итоговое"]
            )
            return

        target_pipeline, target_status = resolve_archive_destination(archive_dest)

        if not target_pipeline or not target_status:
            logger.error(
                f"[DAILY] Сделка {lead_id}: неизвестное назначение '{archive_dest}'"
            )
            self.stats["errors"] += 1
            return

        # Шаг 3: Перенести сделку
        logger.info(
            f"[DAILY] Переношу сделку {lead_id} → "
            f"pipeline={target_pipeline}, status={target_status}"
        )

        success = self.client.move_lead(lead_id, target_pipeline, target_status)

        if not success:
            logger.error(f"[DAILY] Ошибка переноса сделки {lead_id}")
            self.stats["errors"] += 1
            return

        # Шаг 4: Добавить примечание
        close_reason = AmoClient.get_custom_field_value(lead, Fields.CLOSE_REASON) or "—"
        note_text = (
            f"📦 Архивировано автоматически\n"
            f"Назначение: {archive_dest}\n"
            f"Причина закрытия: {close_reason}\n"
            f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        self.client.add_note(lead_id, note_text)

        # Шаг 5: Создать задачу на дату возврата (если есть)
        return_date_str = AmoClient.get_custom_field_value(lead, Fields.RETURN_DATE)
        if return_date_str:
            self._create_return_task(lead, return_date_str)

        self.stats["archived_ok"] += 1
        logger.info(f"[DAILY] ✅ Сделка {lead_id} архивирована → {archive_dest}")

    # ─── Валидация полей ─────────────────────────────────────────

    def _validate_archive_fields(self, lead: dict) -> list[str]:
        """
        Проверить обязательные поля для архивации.
        
        Returns: список названий незаполненных полей (пустой = всё ок)
        """
        missing = []
        for field_id in ARCHIVE_REQUIRED_FIELDS:
            value = AmoClient.get_custom_field_value(lead, field_id)
            if not value:
                field_name = ARCHIVE_REQUIRED_FIELD_NAMES.get(
                    field_id, f"field_{field_id}"
                )
                missing.append(field_name)
        return missing

    def _handle_incomplete_lead(self, lead: dict, missing_fields: list[str]):
        """Обработка сделки с незаполненными полями."""
        lead_id = lead["id"]
        responsible = lead.get("responsible_user_id", Users.EMPLOYEE_2_SALES)

        fields_list = ", ".join(missing_fields)
        text = (
            f"⚠️ Не хватает данных для архивирования!\n"
            f"Незаполненные поля: {fields_list}\n"
            f"Заполните поля и оставьте сделку в статусе 'К архивированию'"
        )

        logger.warning(
            f"[DAILY] Сделка {lead_id}: не хватает полей — {fields_list}"
        )

        # Задача ответственному
        self.client.create_task(
            lead_id=lead_id,
            text=text,
            responsible_user_id=responsible,
            deadline_seconds=4 * 3600,  # 4 часа
            task_type_id=3,
        )

        # Примечание
        self.client.add_note(
            lead_id,
            f"⚠️ Архивация отложена: не заполнены поля ({fields_list})"
        )

    # ─── Задача на дату возврата ─────────────────────────────────

    def _create_return_task(self, lead: dict, return_date_str: str):
        """Создать задачу на дату возврата из архива."""
        lead_id = lead["id"]
        responsible = lead.get("responsible_user_id", Users.EMPLOYEE_2_SALES)

        try:
            # amoCRM хранит дату как timestamp или строку
            if return_date_str.isdigit():
                return_date = datetime.fromtimestamp(int(return_date_str))
            else:
                # Пробуем разные форматы
                for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        return_date = datetime.strptime(return_date_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    logger.warning(
                        f"[DAILY] Не удалось распарсить дату возврата: {return_date_str}"
                    )
                    return

            # Создаём задачу на эту дату
            lead_name = lead.get("name", "Без названия")
            text = (
                f"🔄 Возврат из архива: {lead_name}\n"
                f"Проверить актуальность и решить: вернуть в работу или оставить в архиве"
            )

            task = self.client.create_task_at_date(
                lead_id=lead_id,
                text=text,
                responsible_user_id=responsible,
                deadline_date=return_date,
                task_type_id=1,
            )

            if task:
                self.stats["return_tasks_created"] += 1
                logger.info(
                    f"[DAILY] Задача на возврат: сделка {lead_id}, "
                    f"дата {return_date.strftime('%d.%m.%Y')}"
                )

        except Exception as e:
            logger.error(f"[DAILY] Ошибка создания задачи на возврат: {e}")

    # ─── 2. Проверка дат возврата в архивах ──────────────────────

    def _check_return_dates(self):
        """
        Проверить архивные сделки с наступившей датой возврата.
        Создать задачу ответственному.
        """
        logger.info("[DAILY] Проверка дат возврата в архивных воронках...")

        archive_pipelines = [PIPELINE_ARCHIVE_DIRECTIONS, PIPELINE_ARCHIVE_SOZ]

        for pipeline_id in archive_pipelines:
            # Получаем все сделки из архивной воронки
            page = 1
            while True:
                leads = self.client.get_leads(
                    pipeline_id=pipeline_id,
                    page=page,
                )
                if not leads:
                    break

                for lead in leads:
                    self._check_lead_return_date(lead)

                if len(leads) < 250:
                    break
                page += 1

    def _check_lead_return_date(self, lead: dict):
        """Проверить дату возврата одной архивной сделки."""
        return_date_str = AmoClient.get_custom_field_value(lead, Fields.RETURN_DATE)
        if not return_date_str:
            return

        try:
            if return_date_str.isdigit():
                return_date = datetime.fromtimestamp(int(return_date_str))
            else:
                for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                    try:
                        return_date = datetime.strptime(return_date_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return

            # Если дата возврата сегодня или в прошлом
            if return_date.date() <= datetime.now().date():
                lead_id = lead["id"]
                lead_name = lead.get("name", "Без названия")
                responsible = lead.get("responsible_user_id", Users.EMPLOYEE_2_SALES)

                logger.info(
                    f"[DAILY] 🔄 Дата возврата наступила: сделка {lead_id} — '{lead_name}'"
                )

                # Создаём задачу (не автоматический возврат — сначала человек решает)
                text = (
                    f"🔄 ДАТА ВОЗВРАТА НАСТУПИЛА\n"
                    f"Сделка: {lead_name}\n"
                    f"Дата возврата: {return_date.strftime('%d.%m.%Y')}\n"
                    f"Действие: позвонить / проверить актуальность / "
                    f"вернуть в активную воронку или продлить архив"
                )

                self.client.create_task(
                    lead_id=lead_id,
                    text=text,
                    responsible_user_id=responsible,
                    deadline_seconds=24 * 3600,  # 1 день
                    task_type_id=1,
                )
                self.stats["return_tasks_created"] += 1

        except Exception as e:
            logger.debug(f"Error checking return date: {e}")


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def run_daily(dry_run: bool = False) -> dict:
    """Точка входа для запуска ежедневной архивации."""
    archiver = DailyArchiver(dry_run=dry_run)
    return archiver.run()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    dry = "--dry-run" in sys.argv
    if dry:
        print("🔍 DRY-RUN режим — сделки НЕ будут перенесены")
    stats = run_daily(dry_run=dry)
    print(f"\nРезультат: {stats}")
