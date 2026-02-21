"""Unit tests for orchestrator state machine transitions (black-box, per interfaces-v2.md)."""

from __future__ import annotations

import pytest

from app.orchestrator.state_machine import (
    GATED_PHASES,
    PHASE_TRANSITIONS,
    UNGATED_PHASES,
    PhaseStatus,
    validate_transition,
)


class TestPhaseStatusEnum:
    def test_enum_values(self):
        assert PhaseStatus.PENDING.value == "pending"
        assert PhaseStatus.RUNNING.value == "running"
        assert PhaseStatus.SCORING.value == "scoring"
        assert PhaseStatus.PASSED.value == "passed"
        assert PhaseStatus.FAILED.value == "failed"
        assert PhaseStatus.ITERATING.value == "iterating"
        assert PhaseStatus.ESCALATED.value == "escalated"
        assert PhaseStatus.SKIPPED.value == "skipped"

    def test_all_statuses_present(self):
        assert len(PhaseStatus) == 8

    def test_gated_phases_exact(self):
        assert GATED_PHASES == {1, 3, 7}

    def test_ungated_phases_exact(self):
        assert UNGATED_PHASES == {0, 2, 4, 5, 6}

    def test_gated_and_ungated_disjoint(self):
        assert GATED_PHASES.isdisjoint(UNGATED_PHASES)

    def test_gated_and_ungated_cover_all_phases(self):
        assert GATED_PHASES | UNGATED_PHASES == {0, 1, 2, 3, 4, 5, 6, 7}


class TestTransitionTable:
    def test_all_statuses_in_transition_map(self):
        assert set(PHASE_TRANSITIONS.keys()) == set(PhaseStatus)

    @pytest.mark.parametrize(
        "current,target",
        [
            (PhaseStatus.PENDING, PhaseStatus.RUNNING),
            (PhaseStatus.RUNNING, PhaseStatus.SCORING),
            (PhaseStatus.RUNNING, PhaseStatus.SKIPPED),
            (PhaseStatus.SCORING, PhaseStatus.PASSED),
            (PhaseStatus.SCORING, PhaseStatus.FAILED),
            (PhaseStatus.FAILED, PhaseStatus.ITERATING),
            (PhaseStatus.FAILED, PhaseStatus.ESCALATED),
            (PhaseStatus.ITERATING, PhaseStatus.RUNNING),
            (PhaseStatus.PASSED, PhaseStatus.PENDING),
            (PhaseStatus.SKIPPED, PhaseStatus.PENDING),
        ],
    )
    def test_valid_transitions(self, current: PhaseStatus, target: PhaseStatus):
        assert validate_transition(current, target) is True
        assert target in PHASE_TRANSITIONS[current]

    @pytest.mark.parametrize(
        "current,target",
        [
            # RUNNING -> PASSED not valid directly (must go through SCORING)
            (PhaseStatus.RUNNING, PhaseStatus.PASSED),
            # ESCALATED is terminal — no outbound transitions
            (PhaseStatus.ESCALATED, PhaseStatus.PENDING),
            (PhaseStatus.ESCALATED, PhaseStatus.RUNNING),
            (PhaseStatus.ESCALATED, PhaseStatus.SCORING),
            (PhaseStatus.ESCALATED, PhaseStatus.PASSED),
            (PhaseStatus.ESCALATED, PhaseStatus.FAILED),
            (PhaseStatus.ESCALATED, PhaseStatus.ITERATING),
            (PhaseStatus.ESCALATED, PhaseStatus.SKIPPED),
            # Other invalid transitions
            (PhaseStatus.PENDING, PhaseStatus.SCORING),
            (PhaseStatus.PENDING, PhaseStatus.PASSED),
            (PhaseStatus.SCORING, PhaseStatus.RUNNING),
            (PhaseStatus.PASSED, PhaseStatus.RUNNING),
            (PhaseStatus.SKIPPED, PhaseStatus.SCORING),
            (PhaseStatus.ITERATING, PhaseStatus.PASSED),
        ],
    )
    def test_invalid_transitions(self, current: PhaseStatus, target: PhaseStatus):
        assert validate_transition(current, target) is False

    def test_escalated_is_terminal(self):
        """ESCALATED has no outbound transitions — it's a terminal state."""
        assert PHASE_TRANSITIONS[PhaseStatus.ESCALATED] == []
