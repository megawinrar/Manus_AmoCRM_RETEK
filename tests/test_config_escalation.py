"""
Tests for config.py auto_escalate_priority function and build_lead_name.
Covers lines 656-703 (auto_escalate_priority) and line 344 (resolve_archive_destination else branch).
"""
import pytest
from unittest.mock import patch
import os


class TestAutoEscalatePriority:
    """Tests for auto_escalate_priority function in config.py."""

    def setup_method(self):
        """Import the function under test."""
        from src.microservice.config import auto_escalate_priority
        self.escalate = auto_escalate_priority

    def test_empty_deadline_no_escalation(self):
        """Empty deadline string returns current priority unchanged."""
        result = self.escalate("Р3", "")
        assert result == ("Р3", False, "")

    def test_none_deadline_no_escalation(self):
        """None-like empty deadline returns current priority unchanged."""
        result = self.escalate("Р4", "")
        assert result == ("Р4", False, "")

    def test_deadline_far_away_no_escalation(self):
        """Deadline > 5 days away: no escalation."""
        result = self.escalate("Р3", "2026-07-01", today_str="2026-06-10")
        assert result == ("Р3", False, "")

    def test_deadline_within_5_days_escalate_to_p2(self):
        """Deadline within 5 days (120h): escalate Р3 → Р2."""
        result = self.escalate("Р3", "2026-06-14", today_str="2026-06-10")
        new_priority, escalated, reason = result
        assert escalated is True
        assert new_priority == "Р2"
        assert "дедлайн" in reason

    def test_deadline_within_48h_escalate_to_p1(self):
        """Deadline within 48 hours: escalate Р3 → Р1."""
        result = self.escalate("Р3", "2026-06-11", today_str="2026-06-10")
        new_priority, escalated, reason = result
        assert escalated is True
        assert new_priority == "Р1"
        assert "Р1" in reason

    def test_deadline_passed_escalate_to_p1(self):
        """Deadline already passed: escalate to Р1."""
        result = self.escalate("Р3", "2026-06-05", today_str="2026-06-10")
        new_priority, escalated, reason = result
        assert escalated is True
        assert new_priority == "Р1"

    def test_already_p1_no_escalation(self):
        """Already Р1 — cannot escalate further."""
        result = self.escalate("Р1", "2026-06-11", today_str="2026-06-10")
        new_priority, escalated, reason = result
        assert escalated is False
        assert new_priority == "Р1"

    def test_already_p2_deadline_within_5_days_no_escalation(self):
        """Already Р2, deadline within 5 days — no escalation needed."""
        result = self.escalate("Р2", "2026-06-14", today_str="2026-06-10")
        new_priority, escalated, reason = result
        assert escalated is False
        assert new_priority == "Р2"

    def test_p2_deadline_within_48h_escalate_to_p1(self):
        """Р2 with deadline within 48h — escalate to Р1."""
        result = self.escalate("Р2", "2026-06-11", today_str="2026-06-10")
        new_priority, escalated, reason = result
        assert escalated is True
        assert new_priority == "Р1"

    def test_p4_deadline_within_5_days_escalate_to_p2(self):
        """Р4 with deadline within 5 days — escalate to Р2."""
        result = self.escalate("Р4", "2026-06-14", today_str="2026-06-10")
        new_priority, escalated, reason = result
        assert escalated is True
        assert new_priority == "Р2"

    def test_p4_deadline_within_48h_escalate_to_p1(self):
        """Р4 with deadline within 48h — escalate to Р1."""
        result = self.escalate("Р4", "2026-06-11", today_str="2026-06-10")
        new_priority, escalated, reason = result
        assert escalated is True
        assert new_priority == "Р1"

    def test_deadline_format_dd_mm_yyyy(self):
        """Deadline in DD.MM.YYYY format is parsed correctly."""
        result = self.escalate("Р3", "11.06.2026", today_str="2026-06-10")
        new_priority, escalated, reason = result
        assert escalated is True
        assert new_priority == "Р1"

    def test_invalid_deadline_format(self):
        """Invalid deadline format returns no escalation."""
        result = self.escalate("Р3", "not-a-date", today_str="2026-06-10")
        assert result == ("Р3", False, "")

    def test_deadline_numeric_only_no_escalation(self):
        """Deadline with only numbers (no separators) returns no escalation."""
        result = self.escalate("Р3", "20260610", today_str="2026-06-10")
        assert result == ("Р3", False, "")

    def test_no_today_str_uses_real_today(self):
        """When today_str is None, uses date.today()."""
        # Use a deadline far in the future so no escalation
        result = self.escalate("Р3", "2030-12-31")
        assert result == ("Р3", False, "")

    def test_exactly_48h_boundary(self):
        """Exactly 2 days (48h) — should trigger P1 escalation."""
        result = self.escalate("Р3", "2026-06-12", today_str="2026-06-10")
        new_priority, escalated, reason = result
        assert escalated is True
        assert new_priority == "Р1"

    def test_exactly_5_days_boundary(self):
        """Exactly 5 days (120h) — should trigger P2 escalation."""
        result = self.escalate("Р3", "2026-06-15", today_str="2026-06-10")
        new_priority, escalated, reason = result
        assert escalated is True
        assert new_priority == "Р2"

    def test_6_days_no_escalation(self):
        """6 days away — no escalation."""
        result = self.escalate("Р3", "2026-06-16", today_str="2026-06-10")
        assert result == ("Р3", False, "")


class TestResolveArchiveDestinationElseBranch:
    """Test the else branch (line 344) in resolve_archive_destination."""

    def test_unknown_pipeline_returns_zero_status(self):
        """When pipeline_id is neither DIRECTIONS nor SOZ, status_id = 0."""
        from src.microservice.config import (
            resolve_archive_destination,
            ARCHIVE_ROUTING,
            PIPELINE_ARCHIVE_DIRECTIONS,
            PIPELINE_ARCHIVE_SOZ,
        )
        # Temporarily add a route with an unknown pipeline
        test_key = "__test_unknown_pipeline__"
        ARCHIVE_ROUTING[test_key] = (99999, "SOME_STATUS")
        try:
            pipeline_id, status_id = resolve_archive_destination(test_key)
            assert pipeline_id == 99999
            assert status_id == 0
        finally:
            del ARCHIVE_ROUTING[test_key]

    def test_unknown_archive_dest_returns_none(self):
        """Unknown archive destination value returns (None, None)."""
        from src.microservice.config import resolve_archive_destination
        result = resolve_archive_destination("TOTALLY_UNKNOWN_VALUE")
        assert result == (None, None)


class TestBuildLeadNameConfig:
    """Tests for build_lead_name from config.py."""

    def test_basic_name(self):
        """Build name with priority, customer, deadline."""
        from src.microservice.config import build_lead_name, PRIORITY_LABELS
        # Get a valid priority enum id
        priority_id = list(PRIORITY_LABELS.keys())[0]
        result = build_lead_name(
            priority_enum_id=priority_id,
            customer="ООО Рога и Копыта",
            deadline_str="15.06",
        )
        assert PRIORITY_LABELS[priority_id] in result
        assert "15.06" in result

    def test_unknown_priority_id(self):
        """Unknown priority enum ID uses [P?] prefix."""
        from src.microservice.config import build_lead_name
        result = build_lead_name(
            priority_enum_id=999999,
            customer="Test",
            deadline_str="",
        )
        assert "[P?]" in result

    def test_long_customer_truncated(self):
        """Customer name longer than 20 chars is truncated."""
        from src.microservice.config import build_lead_name, PRIORITY_LABELS
        priority_id = list(PRIORITY_LABELS.keys())[0]
        long_name = "А" * 50
        result = build_lead_name(
            priority_enum_id=priority_id,
            customer=long_name,
            deadline_str="",
        )
        # Customer part should be max 20 chars
        assert len(long_name[:20]) == 20

    def test_empty_customer_and_deadline(self):
        """Empty customer and deadline still produces a valid name."""
        from src.microservice.config import build_lead_name, PRIORITY_LABELS
        priority_id = list(PRIORITY_LABELS.keys())[0]
        result = build_lead_name(
            priority_enum_id=priority_id,
            customer="",
            deadline_str="",
        )
        assert PRIORITY_LABELS[priority_id] in result
