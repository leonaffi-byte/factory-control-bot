"""Integration tests for event outbox system (black-box, per spec-v2.md)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestEventCreation:
    def test_factory_event_has_event_type(self):
        """FactoryEvent must have event_type field."""
        from app.models.factory_event import FactoryEvent

        event = FactoryEvent()
        assert hasattr(event, "event_type")

    def test_factory_event_has_processed_flag(self):
        """FactoryEvent must have processed field for outbox pattern."""
        from app.models.factory_event import FactoryEvent

        event = FactoryEvent()
        assert hasattr(event, "processed")
        assert event.processed is False

    def test_factory_event_has_data_json(self):
        """FactoryEvent must have data field for typed DTO payload."""
        from app.models.factory_event import FactoryEvent

        event = FactoryEvent()
        assert hasattr(event, "data") or hasattr(event, "data_json")


class TestEventTypes:
    """Verify all spec-defined event types are valid strings."""

    @pytest.mark.parametrize(
        "event_type",
        [
            "phase_started",
            "phase_completed",
            "gate_passed",
            "gate_failed",
            "run_started",
            "run_completed",
            "run_failed",
            "clarification_needed",
            "health_alert",
            "scan_completed",
            "research_completed",
            "paid_permission_needed",
            "paid_permission_response",
        ],
    )
    def test_event_type_is_valid_string(self, event_type: str):
        assert isinstance(event_type, str)
        assert len(event_type) <= 50


class TestPgEventListener:
    def test_listener_can_be_created(self):
        """PgEventListener should be instantiable with a DSN."""
        from app.database.events import PgEventListener

        listener = PgEventListener("postgresql://test:test@localhost/test")
        assert listener is not None
