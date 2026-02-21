"""Phase execution modules for the factory pipeline."""
from __future__ import annotations

from app.orchestrator.phases.phase0_assessment import Phase0AssessmentExecutor
from app.orchestrator.phases.phase1_requirements import Phase1RequirementsExecutor
from app.orchestrator.phases.phase2_brainstorm import Phase2BrainstormExecutor
from app.orchestrator.phases.phase3_architecture import Phase3ArchitectureExecutor
from app.orchestrator.phases.phase4_implementation import Phase4ImplementationExecutor
from app.orchestrator.phases.phase5_review import Phase5ReviewExecutor
from app.orchestrator.phases.phase6_testing import Phase6TestingExecutor
from app.orchestrator.phases.phase7_release import Phase7ReleaseExecutor

# Mapping of phase number -> executor class
PHASE_EXECUTORS: dict[int, type] = {
    0: Phase0AssessmentExecutor,
    1: Phase1RequirementsExecutor,
    2: Phase2BrainstormExecutor,
    3: Phase3ArchitectureExecutor,
    4: Phase4ImplementationExecutor,
    5: Phase5ReviewExecutor,
    6: Phase6TestingExecutor,
    7: Phase7ReleaseExecutor,
}

__all__ = [
    "Phase0AssessmentExecutor",
    "Phase1RequirementsExecutor",
    "Phase2BrainstormExecutor",
    "Phase3ArchitectureExecutor",
    "Phase4ImplementationExecutor",
    "Phase5ReviewExecutor",
    "Phase6TestingExecutor",
    "Phase7ReleaseExecutor",
    "PHASE_EXECUTORS",
]
