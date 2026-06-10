"""
Tests for domain layer.
"""
import pytest
from src.domain.enums import Priority, Direction, SituationType, ActiveStatuses, Fields, Pipelines, Users
from src.domain.rules import resolve_routing, auto_escalate_priority, build_lead_name, resolve_archive_destination
from src.domain.models import TenderFile, ClassificationResult, DeduplicationResult


class TestEnums:
    def test_priority_values(self):
        assert Priority.P1 == "Р1 — Срочно"
        assert Priority.P2 == "Р2 — Быстрые деньги"
        assert Priority.P3 == "Р3 — Средние деньги"
        assert Priority.P4 == "Р4 — Наблюдаем"

    def test_direction_values(self):
        assert "HSS-06" in Direction.HSS_06
        assert "CARB-02" in Direction.CARB_02

    def test_situation_type_values(self):
        assert SituationType.SOZ == "СОЗ"
        assert SituationType.REAL_TENDER == "Реальные торги"

    def test_active_statuses_exist(self):
        assert ActiveStatuses.LLM_RECOGNIZED > 0
        assert ActiveStatuses.TO_ARCHIVE > 0

    def test_users_exist(self):
        assert Users.EMPLOYEE_2_SALES > 0
        assert Users.EMPLOYEE_3_BUYER > 0


class TestRouting:
    def test_p1_real_tender_routes_to_purchasing(self):
        status, user = resolve_routing("Р1", "Запрос котировок / реальные торги")
        assert status == ActiveStatuses.PURCHASING
        assert user == Users.EMPLOYEE_3_BUYER

    def test_p1_soz_routes_to_soz_call(self):
        status, user = resolve_routing("Р1", "СОЗ")
        assert status == ActiveStatuses.SOZ_CALL
        assert user == Users.EMPLOYEE_2_SALES

    def test_p4_routes_to_archive(self):
        status, user = resolve_routing("Р4", "СОЗ")
        assert status == ActiveStatuses.TO_ARCHIVE

    def test_unknown_routes_to_check(self):
        status, user = resolve_routing("Р2", "Неясно")
        assert status == ActiveStatuses.CHECK_EMPLOYEE2

    def test_not_our_assortment_routes_to_archive(self):
        status, user = resolve_routing("Р1", "Не наш ассортимент")
        assert status == ActiveStatuses.TO_ARCHIVE

    def test_fallback_for_unknown_combination(self):
        status, user = resolve_routing("Р5", "Что-то новое")
        assert status == ActiveStatuses.CHECK_EMPLOYEE2
        assert user == Users.EMPLOYEE_2_SALES


class TestEscalation:
    def test_deadline_overdue_escalates_to_p1(self):
        new_priority = auto_escalate_priority("Р3", -1)
        assert "Р1" in new_priority

    def test_deadline_2days_escalates_to_p1(self):
        new_priority = auto_escalate_priority("Р3", 2)
        assert "Р1" in new_priority

    def test_deadline_5days_escalates_to_p2(self):
        new_priority = auto_escalate_priority("Р3", 4)
        assert "Р2" in new_priority

    def test_no_escalation_far_deadline(self):
        new_priority = auto_escalate_priority("Р3", 30)
        assert new_priority == "Р3"

    def test_p1_stays_p1_regardless(self):
        new_priority = auto_escalate_priority("Р1", 30)
        assert new_priority == "Р1"


class TestBuildLeadName:
    def test_build_name_p1(self):
        name = build_lead_name(215673, "ООО Завод", "10.06")
        assert "[P1]" in name
        assert "Завод" in name
        assert "10.06" in name

    def test_build_name_p2(self):
        name = build_lead_name(215675, "АО Рога", "15.07")
        assert "[P2]" in name
        assert "Рога" in name

    def test_build_name_unknown_priority(self):
        name = build_lead_name(999999, "Тест", "01.01")
        assert "[P?]" in name


class TestArchiveRouting:
    def test_archive_directions_spec_drawing(self):
        pipeline, status = resolve_archive_destination("Архив — направления / Специнструмент по чертежам")
        assert pipeline == Pipelines.ARCHIVE_DIRECTIONS
        assert status > 0

    def test_archive_soz_waiting(self):
        pipeline, status = resolve_archive_destination("Архив — СОЗ / Ждём реальные торги")
        assert pipeline == Pipelines.ARCHIVE_SOZ
        assert status > 0

    def test_archive_unknown(self):
        pipeline, status = resolve_archive_destination("Неизвестное направление")
        assert pipeline is None
        assert status is None


class TestModels:
    def test_tender_file_creation(self):
        tf = TenderFile(filename="test.pdf", file_hash="abc123", source_path="/tmp/test.pdf")
        assert tf.filename == "test.pdf"
        assert tf.file_hash == "abc123"
        assert tf.file_size == 0

    def test_classification_result(self):
        cr = ClassificationResult(
            customer="ООО Завод",
            nmc=1500000.0,
            direction="HSS-06",
            priority="Р2 — Быстрые деньги",
            situation_type="Реальные торги"
        )
        assert cr.customer == "ООО Завод"
        assert cr.nmc == 1500000.0

    def test_deduplication_result_new(self):
        dr = DeduplicationResult(is_new=True)
        assert dr.is_new is True
        assert dr.is_exact_duplicate is False

    def test_deduplication_result_duplicate(self):
        dr = DeduplicationResult(is_new=False, is_exact_duplicate=True, existing_lead_id=12345)
        assert dr.is_new is False
        assert dr.existing_lead_id == 12345
