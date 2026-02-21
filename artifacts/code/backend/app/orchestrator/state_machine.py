"""Factory pipeline state machine definitions."""
from __future__ import annotations

from enum import Enum


class PhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SCORING = "scoring"
    PASSED = "passed"
    FAILED = "failed"
    ITERATING = "iterating"
    ESCALATED = "escalated"
    SKIPPED = "skipped"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"


PHASE_TRANSITIONS: dict[PhaseStatus, list[PhaseStatus]] = {
    PhaseStatus.PENDING: [PhaseStatus.RUNNING],
    PhaseStatus.RUNNING: [PhaseStatus.SCORING, PhaseStatus.SKIPPED],
    PhaseStatus.SCORING: [PhaseStatus.PASSED, PhaseStatus.FAILED],
    PhaseStatus.PASSED: [PhaseStatus.PENDING],
    PhaseStatus.FAILED: [PhaseStatus.ITERATING, PhaseStatus.ESCALATED],
    PhaseStatus.ITERATING: [PhaseStatus.RUNNING],
    PhaseStatus.ESCALATED: [],
    PhaseStatus.SKIPPED: [PhaseStatus.PENDING],
}

GATED_PHASES: set[int] = {1, 3, 7}
UNGATED_PHASES: set[int] = {0, 2, 4, 5, 6}


def validate_transition(current: PhaseStatus, target: PhaseStatus) -> bool:
    return target in PHASE_TRANSITIONS.get(current, [])
