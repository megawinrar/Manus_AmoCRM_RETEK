"""
Ежемесячная ревизия — cron_monthly.

Задачи:
1. Ревизия архива:
   - Карточки без даты возврата
   - Карточки без причины закрытия
   - СОЗ, которые не вернулись в реальные торги
2. Статистика по направлениям
3. Отчёт руководителю (задача + примечание)
"""

import logging
import time
from datetime import datetime
from collections import Counter

from .amo_client import AmoClient
from .config import (
    PIPELINE_ACTIVE,
    PIPELINE_ARCHIVE_DIRECTIONS,
    PIPELINE_ARCHIVE_SOZ,
    ActiveStatuses,
    Fields,
    Users,
)

logger = logging.getLogger(__name__)


class MonthlyRevision:
    """Ежемесячная ревизия архива."""

    def __init__(self, dry_run: bool = False):
        self.client = AmoClient(dry_run=dry_run)
        self.dry_run = dry_run
        self.report = {
            "date": datetime.now().strftime("%d.%m.%Y"),
            "archive_directions_total": 0,
            "archive_soz_total": 0,
            "active_total": 0,
            "no_return_date": [],
            "no_close_reason": [],
            "soz_not_returned": [],
            "directions_breakdown": Counter(),
            "priorities_breakdown": Counter(),
        }

    def run(self):
        """Запуск ежемесячной ревизии."""
        logger.info("=" * 60)
        logger.info(f"[MONTHLY] Начало ревизии — {datetime.now().isoformat()}")
        logger.info("=" * 60)

        try:
            self._audit_archive_directions()
            self._audit_archive_soz()
            self._audit_active_pipeline()
            self._generate_report()
        except Exception as e:
            logger.error(f"[MONTHLY] Критическая ошибка: {e}", exc_info=True)

        logger.info(f"[MONTHLY] Завершено")
        return self.report

    # ─── 1. Аудит Архив — Направления ────────────────────────────

    def _audit_archive_directions(self):
        """Проверить все сделки в архиве направлений."""
        logger.info("[MONTHLY] Аудит: Архив — Направления...")

        all_leads = self._get_all_pipeline_leads(PIPELINE_ARCHIVE_DIRECTIONS)
        self.report["archive_directions_total"] = len(all_leads)

        for lead in all_leads:
            lead_id = lead["id"]
            lead_name = lead.get("name", "?")

            # Проверка: есть ли дата возврата или причина закрытия
            return_date = AmoClient.get_custom_field_value(lead, Fields.RETURN_DATE)
            close_reason = AmoClient.get_custom_field_value(lead, Fields.CLOSE_REASON)

            if not return_date and not close_reason:
                # Ни даты возврата, ни причины — ошибка заполнения
                self.report["no_return_date"].append({
                    "id": lead_id,
                    "name": lead_name[:50],
                })

            if not close_reason:
                self.report["no_close_reason"].append({
                    "id": lead_id,
                    "name": lead_name[:50],
                })

            # Статистика по направлениям
            direction = AmoClient.get_custom_field_value(lead, Fields.DIRECTION)
            if direction:
                self.report["directions_breakdown"][direction] += 1

    # ─── 2. Аудит Архив — СОЗ ────────────────────────────────────

    def _audit_archive_soz(self):
        """Проверить все сделки в архиве СОЗ."""
        logger.info("[MONTHLY] Аудит: Архив — СОЗ / развитие...")

        all_leads = self._get_all_pipeline_leads(PIPELINE_ARCHIVE_SOZ)
        self.report["archive_soz_total"] = len(all_leads)

        for lead in all_leads:
            lead_id = lead["id"]
            lead_name = lead.get("name", "?")

            # СОЗ без даты возврата — потенциально забытые
            return_date = AmoClient.get_custom_field_value(lead, Fields.RETURN_DATE)
            if not return_date:
                self.report["soz_not_returned"].append({
                    "id": lead_id,
                    "name": lead_name[:50],
                })

    # ─── 3. Аудит активной воронки ───────────────────────────────

    def _audit_active_pipeline(self):
        """Общая статистика по активной воронке."""
        logger.info("[MONTHLY] Аудит: Активная воронка...")

        all_leads = self._get_all_pipeline_leads(PIPELINE_ACTIVE)
        self.report["active_total"] = len(all_leads)

        for lead in all_leads:
            priority = AmoClient.get_custom_field_value(lead, Fields.PRIORITY)
            if priority:
                self.report["priorities_breakdown"][priority] += 1

    # ─── 4. Генерация отчёта ─────────────────────────────────────

    def _generate_report(self):
        """Сформировать отчёт и создать задачу руководителю."""
        logger.info("[MONTHLY] Формирование отчёта...")

        # Формируем текст отчёта
        lines = [
            f"📊 ЕЖЕМЕСЯЧНЫЙ ОТЧЁТ — {self.report['date']}",
            "",
            "═══ ОБЩАЯ СТАТИСТИКА ═══",
            f"Активная воронка: {self.report['active_total']} сделок",
            f"Архив — Направления: {self.report['archive_directions_total']} сделок",
            f"Архив — СОЗ: {self.report['archive_soz_total']} сделок",
            "",
        ]

        # Приоритеты
        if self.report["priorities_breakdown"]:
            lines.append("═══ ПРИОРИТЕТЫ (активные) ═══")
            for priority, count in sorted(self.report["priorities_breakdown"].items()):
                lines.append(f"  {priority}: {count}")
            lines.append("")

        # Направления
        if self.report["directions_breakdown"]:
            lines.append("═══ НАПРАВЛЕНИЯ (архив) ═══")
            for direction, count in self.report["directions_breakdown"].most_common(10):
                lines.append(f"  {direction}: {count}")
            lines.append("")

        # Проблемы
        problems = []
        if self.report["no_return_date"]:
            problems.append(
                f"⚠️ Без даты возврата И причины: {len(self.report['no_return_date'])} шт."
            )
        if self.report["no_close_reason"]:
            problems.append(
                f"⚠️ Без причины закрытия: {len(self.report['no_close_reason'])} шт."
            )
        if self.report["soz_not_returned"]:
            problems.append(
                f"⚠️ СОЗ без даты возврата: {len(self.report['soz_not_returned'])} шт."
            )

        if problems:
            lines.append("═══ ПРОБЛЕМЫ ═══")
            lines.extend(problems)
            lines.append("")

            # Примеры проблемных карточек (до 5)
            if self.report["no_return_date"][:5]:
                lines.append("Примеры (без даты/причины):")
                for item in self.report["no_return_date"][:5]:
                    lines.append(f"  • [{item['id']}] {item['name']}")
        else:
            lines.append("✅ Проблем не обнаружено")

        report_text = "\n".join(lines)
        logger.info(f"[MONTHLY] Отчёт:\n{report_text}")

        # Создаём задачу руководителю
        if Users.MANAGER:
            # Берём первую сделку из активной воронки для привязки задачи
            # (или создаём без привязки если нет сделок)
            active_leads = self.client.get_leads(
                pipeline_id=PIPELINE_ACTIVE, limit=1, with_fields=False
            )

            if active_leads:
                lead_id = active_leads[0]["id"]
                self.client.create_task(
                    lead_id=lead_id,
                    text=f"📊 Ежемесячный отчёт готов. Проверить архив и проблемные карточки.\n\n{report_text[:500]}",
                    responsible_user_id=Users.MANAGER,
                    deadline_seconds=3 * 24 * 3600,  # 3 дня
                    task_type_id=3,
                )

                # Полный отчёт — в примечание
                self.client.add_note(lead_id, report_text)

            logger.info("[MONTHLY] Задача руководителю создана")

    # ─── Утилиты ─────────────────────────────────────────────────

    def _get_all_pipeline_leads(self, pipeline_id: int) -> list[dict]:
        """Получить все сделки из воронки (с пагинацией)."""
        all_leads = []
        page = 1
        while True:
            leads = self.client.get_leads(
                pipeline_id=pipeline_id,
                page=page,
            )
            if not leads:
                break
            all_leads.extend(leads)
            if len(leads) < 250:
                break
            page += 1
        return all_leads


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def run_monthly(dry_run: bool = False) -> dict:
    """Точка входа для запуска ежемесячной ревизии."""
    revision = MonthlyRevision(dry_run=dry_run)
    return revision.run()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    dry = "--dry-run" in sys.argv
    if dry:
        print("🔍 DRY-RUN режим")
    report = run_monthly(dry_run=dry)
    print(f"\nОтчёт: {report['date']}")
    print(f"  Активных: {report['active_total']}")
    print(f"  Архив направления: {report['archive_directions_total']}")
    print(f"  Архив СОЗ: {report['archive_soz_total']}")
