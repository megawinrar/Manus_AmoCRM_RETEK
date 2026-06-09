"""
Ежечасный контроль — cron_hourly.

Задачи:
1. Контроль Р1/Р2 — если нет активной задачи или задача просрочена → уведомление руководителю
2. Поиск сделок без «Следующего действия» → задача ответственному
3. Контроль просроченных задач → уведомление
4. Автоэскалация приоритета по дедлайну (≤ 48ч → Р1)
"""

import logging
import time
from datetime import datetime

from .amo_client import AmoClient
from .config import (
    PIPELINE_ACTIVE,
    ActiveStatuses,
    Fields,
    Users,
    PRIORITY_CONTROL,
    MAX_NO_TASK_P1,
    MAX_NO_TASK_P2,
    PRIORITY_ENUM_IDS,
    PRIORITY_ENUM_TO_NAME,
    PRIORITY_LABELS,
    auto_escalate_priority,
    build_lead_name,
    ESCALATION_NOTE_TEMPLATE,
)

logger = logging.getLogger(__name__)


class HourlyControl:
    """Ежечасный контроль приоритетных сделок."""

    def __init__(self, dry_run: bool = False):
        self.client = AmoClient(dry_run=dry_run)
        self.dry_run = dry_run
        self.stats = {
            "checked": 0,
            "overdue_found": 0,
            "no_next_action": 0,
            "escalated": 0,
            "tasks_created": 0,
            "errors": 0,
        }

    def run(self):
        """Запуск ежечасного контроля."""
        logger.info("=" * 60)
        logger.info(f"[HOURLY] Начало контроля — {datetime.now().isoformat()}")
        logger.info("=" * 60)

        try:
            self._escalate_by_deadline()
            self._control_priority_leads()
            self._control_no_next_action()
            self._control_overdue_tasks()
        except Exception as e:
            logger.error(f"[HOURLY] Критическая ошибка: {e}", exc_info=True)
            self.stats["errors"] += 1

        logger.info(f"[HOURLY] Завершено. Статистика: {self.stats}")
        return self.stats

    # ─── 0. Автоэскалация приоритета по дедлайну ─────────────────

    def _escalate_by_deadline(self):
        """
        Проверить все сделки в активной воронке:
        если дедлайн ≤ 48ч и приоритет ниже Р1 → повысить до Р1.
        Если дедлайн ≤ 5 дней и приоритет ниже Р2 → повысить до Р2.
        При эскалации: PATCH приоритет + переименовать + красная заметка + задача 2ч.
        """
        logger.info("[HOURLY] Автоэскалация по дедлайну...")

        active_statuses = [
            ActiveStatuses.LLM_RECOGNIZED,
            ActiveStatuses.CHECK_EMPLOYEE2,
            ActiveStatuses.SOZ_CALL,
            ActiveStatuses.SOZ_WAIT,
            ActiveStatuses.PURCHASING,
            ActiveStatuses.KP_PREPARING,
            ActiveStatuses.KP_SENT_DEALER,
            ActiveStatuses.DEALER_DECISION,
            ActiveStatuses.BIDDING,
        ]

        for status_id in active_statuses:
            if not status_id:
                continue

            leads = self.client.get_leads(
                pipeline_id=PIPELINE_ACTIVE,
                status_id=status_id,
            )

            for lead in leads:
                result = self._try_escalate_lead(lead)
                if result:
                    self.stats["escalated"] += 1

        if self.stats["escalated"]:
            logger.info(f"[HOURLY] Эскалировано сделок: {self.stats['escalated']}")
        else:
            logger.info("[HOURLY] Эскалация не требуется")

    def _try_escalate_lead(self, lead: dict) -> bool:
        """
        Попытаться эскалировать приоритет одной сделки.
        Returns True если эскалация произошла.
        """
        lead_id = lead["id"]

        # Получаем текущий приоритет (текстовое значение)
        priority_value = AmoClient.get_custom_field_value(lead, Fields.PRIORITY)
        if not priority_value:
            return False

        # Получаем дедлайн (поле "Срок подачи")
        deadline_value = AmoClient.get_custom_field_value(lead, Fields.DEADLINE)
        if not deadline_value:
            return False

        # Проверяем эскалацию
        new_priority, escalated, reason = auto_escalate_priority(
            current_priority=priority_value,
            deadline_str=deadline_value,
        )

        if not escalated:
            return False

        logger.warning(
            f"[HOURLY] 🔴 ЭСКАЛАЦИЯ: сделка {lead_id} "
            f"{priority_value} → {new_priority} | {reason}"
        )

        if self.dry_run:
            logger.info(f"[HOURLY] DRY-RUN: пропускаем PATCH для {lead_id}")
            return True

        # 1. PATCH приоритет
        new_enum_id = PRIORITY_ENUM_IDS.get(new_priority)
        self.client.update_lead(lead_id, {
            "custom_fields_values": [
                {"field_id": Fields.PRIORITY, "values": [{"enum_id": new_enum_id}]}
            ]
        })

        # 2. Переименовать карточку
        customer = AmoClient.get_custom_field_value(lead, Fields.CUSTOMER) or ""
        new_name = build_lead_name(
            priority_enum_id=new_enum_id,
            customer=customer,
            deadline_str=deadline_value,
        )
        self.client.update_lead(lead_id, {"name": new_name})

        # 3. Красная заметка в ленту
        note_text = ESCALATION_NOTE_TEMPLATE.format(
            old_priority=priority_value,
            new_priority=new_priority,
            reason=reason,
            deadline=deadline_value,
        )
        self.client.add_note(lead_id, note_text)

        # 4. Задача на 2 часа
        responsible = lead.get("responsible_user_id", Users.EMPLOYEE_3_PURCHASE)
        self.client.create_task(
            lead_id=lead_id,
            text=(
                f"🔴 СРОЧНО! Приоритет повышен до {new_priority}.\n"
                f"Причина: {reason}\n"
                f"Требуется немедленная реакция!"
            ),
            responsible_user_id=responsible,
            deadline_seconds=2 * 3600,  # 2 часа
            task_type_id=3,
        )

        self.stats["tasks_created"] += 1
        return True

    # ─── 1. Контроль Р1/Р2 ───────────────────────────────────────

    def _control_priority_leads(self):
        """
        Найти сделки с приоритетом Р1/Р2 в активной воронке.
        Проверить что у них есть незавершённая задача.
        Если нет — создать задачу руководителю.
        """
        logger.info("[HOURLY] Контроль приоритетных сделок (Р1/Р2)...")

        # Получаем все сделки из активной воронки
        # Фильтруем по статусам (исключаем "К архивированию")
        active_statuses = [
            ActiveStatuses.LLM_RECOGNIZED,
            ActiveStatuses.CHECK_EMPLOYEE2,
            ActiveStatuses.SOZ_CALL,
            ActiveStatuses.SOZ_WAIT,
            ActiveStatuses.PURCHASING,
            ActiveStatuses.KP_PREPARING,
            ActiveStatuses.KP_SENT_DEALER,
            ActiveStatuses.DEALER_DECISION,
            ActiveStatuses.BIDDING,       # 9. Торги
            ActiveStatuses.PRODUCTION,    # 10. Производство
        ]

        for status_id in active_statuses:
            if not status_id:
                continue

            leads = self.client.get_leads(
                pipeline_id=PIPELINE_ACTIVE,
                status_id=status_id,
            )

            for lead in leads:
                self.stats["checked"] += 1
                self._check_priority_lead(lead)

    def _check_priority_lead(self, lead: dict):
        """Проверить одну приоритетную сделку."""
        lead_id = lead["id"]
        priority = AmoClient.get_custom_field_value(lead, Fields.PRIORITY)

        # Только Р1 и Р2
        if priority not in PRIORITY_CONTROL:
            return

        # Проверяем есть ли активная (незавершённая) задача
        tasks = self.client.get_tasks_for_lead(lead_id)
        active_tasks = [t for t in tasks if not t.get("is_completed")]

        if not active_tasks:
            # Нет активной задачи — проблема!
            self.stats["overdue_found"] += 1
            logger.warning(
                f"[HOURLY] ⚠️ Сделка {lead_id} ({priority}) — нет активной задачи!"
            )
            self._create_control_task(lead, priority, "нет активной задачи")
            return

        # Проверяем просроченность
        now = int(time.time())
        overdue_tasks = [
            t for t in active_tasks
            if t.get("complete_till", 0) < now
        ]

        if overdue_tasks:
            self.stats["overdue_found"] += 1
            overdue_hours = (now - overdue_tasks[0]["complete_till"]) // 3600
            logger.warning(
                f"[HOURLY] ⚠️ Сделка {lead_id} ({priority}) — "
                f"просрочена на {overdue_hours}ч!"
            )
            self._create_control_task(
                lead, priority,
                f"задача просрочена на {overdue_hours}ч"
            )

    def _create_control_task(self, lead: dict, priority: str, reason: str):
        """Создать задачу руководителю о проблеме с приоритетной сделкой."""
        lead_id = lead["id"]
        lead_name = lead.get("name", "Без названия")

        text = (
            f"⚠️ КОНТРОЛЬ {priority}: {reason}\n"
            f"Сделка: {lead_name}\n"
            f"Требуется внимание руководителя"
        )

        task = self.client.create_task(
            lead_id=lead_id,
            text=text,
            responsible_user_id=Users.MANAGER,
            deadline_seconds=2 * 3600,  # 2 часа на реакцию
            task_type_id=3,
        )

        if task:
            self.stats["tasks_created"] += 1

    # ─── 2. Сделки без «Следующего действия» ─────────────────────

    def _control_no_next_action(self):
        """
        Найти сделки в активной воронке без заполненного поля
        «Следующее действие» → создать задачу ответственному.
        """
        logger.info("[HOURLY] Поиск сделок без 'Следующего действия'...")

        # Проверяем статусы где «Следующее действие» обязательно
        check_statuses = [
            ActiveStatuses.CHECK_EMPLOYEE2,
            ActiveStatuses.SOZ_CALL,
            ActiveStatuses.SOZ_WAIT,
            ActiveStatuses.PURCHASING,
            ActiveStatuses.KP_PREPARING,
            ActiveStatuses.KP_SENT_DEALER,
            ActiveStatuses.DEALER_DECISION,
        ]

        for status_id in check_statuses:
            if not status_id:
                continue

            leads = self.client.get_leads(
                pipeline_id=PIPELINE_ACTIVE,
                status_id=status_id,
            )

            for lead in leads:
                next_action = AmoClient.get_custom_field_value(
                    lead, Fields.NEXT_ACTION
                )
                if not next_action:
                    self.stats["no_next_action"] += 1
                    lead_id = lead["id"]
                    responsible = lead.get("responsible_user_id", Users.EMPLOYEE_2_SALES)

                    logger.info(
                        f"[HOURLY] Сделка {lead_id} — нет 'Следующего действия'"
                    )

                    self.client.create_task(
                        lead_id=lead_id,
                        text="Заполнить поле 'Следующее действие' — что планируется дальше?",
                        responsible_user_id=responsible,
                        deadline_seconds=4 * 3600,  # 4 часа
                        task_type_id=3,
                    )
                    self.stats["tasks_created"] += 1

    # ─── 3. Просроченные задачи ──────────────────────────────────

    def _control_overdue_tasks(self):
        """
        Найти все просроченные задачи и уведомить руководителя
        (сводное примечание, не отдельные задачи на каждую).
        """
        logger.info("[HOURLY] Проверка просроченных задач...")

        overdue = self.client.get_overdue_tasks()
        if not overdue:
            logger.info("[HOURLY] Просроченных задач нет")
            return

        # Группируем по ответственному
        by_user = {}
        for task in overdue:
            user_id = task.get("responsible_user_id", 0)
            if user_id not in by_user:
                by_user[user_id] = []
            by_user[user_id].append(task)

        logger.info(
            f"[HOURLY] Найдено {len(overdue)} просроченных задач "
            f"у {len(by_user)} сотрудников"
        )

        # Логируем (задачу руководителю создаём только если >3 просроченных)
        if len(overdue) > 3 and Users.MANAGER:
            # Создаём сводную задачу руководителю (привязываем к первой сделке)
            first_task = overdue[0]
            entity_id = first_task.get("entity_id", 0)
            if entity_id:
                summary = (
                    f"⚠️ ПРОСРОЧКИ: {len(overdue)} задач просрочено.\n"
                    f"Сотрудники: {', '.join(str(u) for u in by_user.keys())}\n"
                    f"Требуется контроль"
                )
                self.client.create_task(
                    lead_id=entity_id,
                    text=summary,
                    responsible_user_id=Users.MANAGER,
                    deadline_seconds=2 * 3600,
                    task_type_id=3,
                )
                self.stats["tasks_created"] += 1


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def run_hourly(dry_run: bool = False) -> dict:
    """Точка входа для запуска ежечасного контроля."""
    control = HourlyControl(dry_run=dry_run)
    return control.run()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    dry = "--dry-run" in sys.argv
    if dry:
        print("🔍 DRY-RUN режим")
    stats = run_hourly(dry_run=dry)
    print(f"\nРезультат: {stats}")
