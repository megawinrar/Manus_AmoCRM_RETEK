"""
Еженедельный контроль — cron_weekly.

Задачи:
1. Найти зависшие карточки (>7 дней в одном статусе) → задача руководителю
2. Проверить WIP-лимиты сотрудников
"""

import logging
import time
from datetime import datetime, timedelta

from .amo_client import AmoClient
from .config import (
    PIPELINE_ACTIVE,
    ActiveStatuses,
    Fields,
    Users,
    STUCK_LEAD_DAYS,
    WIP_LIMIT_EMPLOYEE_2,
    WIP_LIMIT_EMPLOYEE_3,
)

logger = logging.getLogger(__name__)


class WeeklyControl:
    """Еженедельный контроль зависших карточек."""

    def __init__(self, dry_run: bool = False):
        self.client = AmoClient(dry_run=dry_run)
        self.dry_run = dry_run
        self.stats = {
            "total_checked": 0,
            "stuck_found": 0,
            "wip_violations": 0,
            "tasks_created": 0,
        }

    def run(self):
        """Запуск еженедельного контроля."""
        logger.info("=" * 60)
        logger.info(f"[WEEKLY] Начало контроля — {datetime.now().isoformat()}")
        logger.info("=" * 60)

        try:
            self._find_stuck_leads()
            self._check_wip_limits()
        except Exception as e:
            logger.error(f"[WEEKLY] Критическая ошибка: {e}", exc_info=True)

        logger.info(f"[WEEKLY] Завершено. Статистика: {self.stats}")
        return self.stats

    # ─── 1. Зависшие карточки ────────────────────────────────────

    def _find_stuck_leads(self):
        """
        Найти сделки, которые находятся в одном статусе > STUCK_LEAD_DAYS дней.
        
        Используем поле updated_at сделки — если не менялась > 7 дней,
        считаем зависшей.
        """
        logger.info(
            f"[WEEKLY] Поиск зависших карточек (>{STUCK_LEAD_DAYS} дней)..."
        )

        stuck_threshold = int(time.time()) - (STUCK_LEAD_DAYS * 24 * 3600)
        stuck_leads = []

        # Проверяем все статусы кроме "К архивированию" и "LLM распознал"
        check_statuses = [
            ActiveStatuses.CHECK_EMPLOYEE2,
            ActiveStatuses.SOZ_CALL,
            ActiveStatuses.SOZ_WAIT,
            ActiveStatuses.PURCHASING,
            ActiveStatuses.KP_PREPARING,
            ActiveStatuses.KP_SENT_DEALER,
            ActiveStatuses.DEALER_DECISION,
            ActiveStatuses.PRODUCTION,
        ]

        for status_id in check_statuses:
            if not status_id:
                continue

            leads = self.client.get_all_leads_in_status(
                pipeline_id=PIPELINE_ACTIVE,
                status_id=status_id,
            )

            for lead in leads:
                self.stats["total_checked"] += 1
                updated_at = lead.get("updated_at", 0)

                if updated_at and updated_at < stuck_threshold:
                    days_stuck = (int(time.time()) - updated_at) // (24 * 3600)
                    stuck_leads.append({
                        "lead": lead,
                        "days_stuck": days_stuck,
                    })

        self.stats["stuck_found"] = len(stuck_leads)

        if not stuck_leads:
            logger.info("[WEEKLY] Зависших карточек не найдено ✅")
            return

        logger.warning(f"[WEEKLY] Найдено зависших карточек: {len(stuck_leads)}")

        # Создаём задачи руководителю (группируем по 5 для читаемости)
        for i in range(0, len(stuck_leads), 5):
            batch = stuck_leads[i:i+5]
            self._create_stuck_report_task(batch)

    def _create_stuck_report_task(self, stuck_batch: list[dict]):
        """Создать задачу руководителю о зависших карточках."""
        if not Users.MANAGER:
            logger.warning("[WEEKLY] USER_MANAGER не настроен!")
            return

        # Формируем текст задачи
        lines = ["⚠️ ЗАВИСШИЕ КАРТОЧКИ (>7 дней без движения):\n"]
        first_lead_id = stuck_batch[0]["lead"]["id"]

        for item in stuck_batch:
            lead = item["lead"]
            days = item["days_stuck"]
            name = lead.get("name", "Без названия")[:50]
            responsible = lead.get("responsible_user_id", "?")
            lines.append(f"• {name} — {days} дн. (отв: {responsible})")

        text = "\n".join(lines)

        task = self.client.create_task(
            lead_id=first_lead_id,
            text=text,
            responsible_user_id=Users.MANAGER,
            deadline_seconds=2 * 24 * 3600,  # 2 дня на разбор
            task_type_id=3,
        )

        if task:
            self.stats["tasks_created"] += 1

    # ─── 2. WIP-лимиты ──────────────────────────────────────────

    def _check_wip_limits(self):
        """
        Проверить количество сделок в работе у каждого сотрудника.
        Если превышен WIP-лимит → уведомление руководителю.
        """
        logger.info("[WEEKLY] Проверка WIP-лимитов...")

        # Считаем сделки по ответственным
        user_counts = {}

        # Получаем все сделки из активной воронки
        page = 1
        while True:
            leads = self.client.get_leads(
                pipeline_id=PIPELINE_ACTIVE,
                page=page,
                with_fields=False,
            )
            if not leads:
                break

            for lead in leads:
                user_id = lead.get("responsible_user_id", 0)
                status_id = lead.get("status_id", 0)

                # Не считаем "К архивированию"
                if status_id == ActiveStatuses.TO_ARCHIVE:
                    continue

                user_counts[user_id] = user_counts.get(user_id, 0) + 1

            if len(leads) < 250:
                break
            page += 1

        # Проверяем лимиты
        wip_limits = {
            Users.EMPLOYEE_2_SALES: WIP_LIMIT_EMPLOYEE_2,
            Users.EMPLOYEE_3_BUYER: WIP_LIMIT_EMPLOYEE_3,
        }

        for user_id, limit in wip_limits.items():
            if not user_id:
                continue
            count = user_counts.get(user_id, 0)
            if count > limit:
                self.stats["wip_violations"] += 1
                logger.warning(
                    f"[WEEKLY] ⚠️ WIP превышен: user {user_id} — "
                    f"{count}/{limit} сделок"
                )

        logger.info(
            f"[WEEKLY] WIP: "
            + ", ".join(f"user {uid}={cnt}" for uid, cnt in user_counts.items())
        )


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def run_weekly(dry_run: bool = False) -> dict:
    """Точка входа для запуска еженедельного контроля."""
    control = WeeklyControl(dry_run=dry_run)
    return control.run()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    dry = "--dry-run" in sys.argv
    if dry:
        print("🔍 DRY-RUN режим")
    stats = run_weekly(dry_run=dry)
    print(f"\nРезультат: {stats}")
