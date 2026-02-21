"""Factory orchestrator service — drives the full pipeline state machine."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import select, update

from app.models.factory_run import FactoryRun, RunStatus
from app.models.orchestration_state import OrchestrationState
from app.orchestrator.quality_gate import QualityGateResult
from app.orchestrator.state_machine import (
    GATED_PHASES,
    UNGATED_PHASES,
    PhaseStatus,
    validate_transition,
)

if TYPE_CHECKING:
    from app.database.session import AsyncSessionFactory
    from app.services.model_router import ModelRouter

logger = structlog.get_logger()

# Human-readable phase names
PHASE_NAMES: dict[int, str] = {
    0: "Complexity Assessment",
    1: "Requirements Analysis",
    2: "Multi-Model Brainstorm",
    3: "Architecture Design",
    4: "Implementation + Testing",
    5: "Cross-Provider Review",
    6: "Test Execution and Fix Cycle",
    7: "Documentation and Release",
}

MAX_PHASES = 8  # 0-7 inclusive


class OrchestrationError(Exception):
    """Raised when an invalid orchestration operation is attempted."""


class FactoryOrchestrator:
    """
    Drives the factory pipeline state machine.

    Responsibilities:
    - Start / resume / stop pipeline runs
    - Advance phases using validated state transitions
    - Handle quality gate results (SCORING -> PASSED / ITERATING / ESCALATED)
    - Persist OrchestrationState to the database
    """

    def __init__(
        self,
        session_factory: "AsyncSessionFactory",
        model_router: "ModelRouter",
    ) -> None:
        self._session_factory = session_factory
        self._model_router = model_router

    # ── Public API ──────────────────────────────────────────────────────────

    async def start_pipeline(
        self,
        project: object,  # Project model instance
        engine: str,
        tier: int,
        interface_source: str,
    ) -> FactoryRun:
        """
        Create a new FactoryRun + OrchestrationState and kick off Phase 0.

        Args:
            project: Project ORM instance (must have .id and .name).
            engine: Engine identifier (e.g. "claude", "gemini").
            tier: Complexity tier (1, 2, or 3; 0 = auto-detected in Phase 0).
            interface_source: Origin of the request ("telegram" | "cli").

        Returns:
            The newly created FactoryRun record.
        """
        async with self._session_factory() as session:
            run = FactoryRun(
                project_id=project.id,  # type: ignore[attr-defined]
                engine=engine,
                status=RunStatus.RUNNING.value,
                current_phase=0,
                started_at=datetime.now(timezone.utc),
                interface_source=interface_source,
            )
            session.add(run)
            await session.flush()

            state = OrchestrationState(
                run_id=run.id,
                current_phase=0,
                phase_status=PhaseStatus.PENDING.value,
                retry_count=0,
                quality_scores={},
                model_assignments={},
                tier=tier,
                barrier_manifest={},
                interface_source=interface_source,
            )
            session.add(state)
            await session.flush()
            await session.refresh(run)
            await session.refresh(state)

        logger.info(
            "pipeline_started",
            run_id=str(run.id),
            project_id=str(project.id),  # type: ignore[attr-defined]
            engine=engine,
            tier=tier,
            interface_source=interface_source,
        )

        # Transition Phase 0 immediately (ungated — auto-pass)
        await self.advance_phase(run.id)
        return run

    async def resume_pipeline(self, run_id: UUID) -> None:
        """
        Resume a paused or failed pipeline from its current phase.

        Transitions the current phase from PENDING/FAILED back to RUNNING.
        """
        state = await self.get_orchestration_state(run_id)
        if state is None:
            raise OrchestrationError(f"No orchestration state found for run {run_id}")

        current = PhaseStatus(state.phase_status)
        if current not in (PhaseStatus.PENDING, PhaseStatus.FAILED, PhaseStatus.ITERATING):
            raise OrchestrationError(
                f"Cannot resume run {run_id}: current status is {state.phase_status}"
            )

        # Mark run as running again
        async with self._session_factory() as session:
            await session.execute(
                update(FactoryRun)
                .where(FactoryRun.id == run_id)
                .values(status=RunStatus.RUNNING.value)
            )

        await self._transition_phase(run_id, PhaseStatus.RUNNING)
        logger.info("pipeline_resumed", run_id=str(run_id), phase=state.current_phase)

    async def advance_phase(self, run_id: UUID) -> None:
        """
        Advance the pipeline to the next phase after the current one completes.

        For gated phases (1, 3, 7): transitions RUNNING -> SCORING (requires gate).
        For ungated phases (0, 2, 4, 5, 6): transitions RUNNING -> PASSED directly.
        After PASSED, moves to the next phase's PENDING if more phases remain,
        or completes the run if Phase 7 is done.
        """
        state = await self.get_orchestration_state(run_id)
        if state is None:
            raise OrchestrationError(f"No orchestration state found for run {run_id}")

        phase = state.current_phase
        current_status = PhaseStatus(state.phase_status)

        # Allow advancing from PENDING (kick off a phase)
        if current_status == PhaseStatus.PENDING:
            await self._transition_phase(run_id, PhaseStatus.RUNNING)
            current_status = PhaseStatus.RUNNING

        if current_status != PhaseStatus.RUNNING:
            raise OrchestrationError(
                f"Cannot advance phase {phase} from status {state.phase_status}"
            )

        if phase in GATED_PHASES:
            # Gated: move to scoring; gate result will continue the flow
            await self._transition_phase(run_id, PhaseStatus.SCORING)
            logger.info("phase_awaiting_gate", run_id=str(run_id), phase=phase)
        else:
            # Ungated: auto-pass
            await self._transition_phase(run_id, PhaseStatus.PASSED)
            await self._move_to_next_phase(run_id, phase)

    async def handle_gate_result(
        self, run_id: UUID, result: QualityGateResult
    ) -> None:
        """
        Process a quality gate result for the current SCORING phase.

        - score >= threshold -> PASSED, move to next phase
        - 90 <= score < threshold, retry_count < max_retries -> ITERATING -> RUNNING
        - score < 90 after 3 retries -> ESCALATED
        """
        state = await self.get_orchestration_state(run_id)
        if state is None:
            raise OrchestrationError(f"No orchestration state found for run {run_id}")

        phase = state.current_phase
        if PhaseStatus(state.phase_status) != PhaseStatus.SCORING:
            raise OrchestrationError(
                f"handle_gate_result called but phase {phase} is not in SCORING state"
            )

        # Persist the score
        new_scores = dict(state.quality_scores or {})
        new_scores[str(phase)] = result.total_score

        async with self._session_factory() as session:
            await session.execute(
                update(OrchestrationState)
                .where(OrchestrationState.run_id == run_id)
                .values(
                    quality_scores=new_scores,
                    last_gate_feedback=result.feedback,
                )
            )

        logger.info(
            "gate_result_received",
            run_id=str(run_id),
            phase=phase,
            score=result.total_score,
            passed=result.passed,
            iteration=result.iteration,
        )

        from app.config import get_settings
        settings = get_settings()
        max_retries: int = settings.max_quality_retries

        if result.passed:
            await self._transition_phase(run_id, PhaseStatus.PASSED)
            await self._move_to_next_phase(run_id, phase)
        elif state.retry_count < max_retries:
            # Increment retry count and iterate
            async with self._session_factory() as session:
                await session.execute(
                    update(OrchestrationState)
                    .where(OrchestrationState.run_id == run_id)
                    .values(retry_count=state.retry_count + 1)
                )
            await self._transition_phase(run_id, PhaseStatus.FAILED)
            await self._transition_phase(run_id, PhaseStatus.ITERATING)
            await self._transition_phase(run_id, PhaseStatus.RUNNING)
            logger.info(
                "gate_iteration",
                run_id=str(run_id),
                phase=phase,
                retry=state.retry_count + 1,
                score=result.total_score,
            )
        else:
            reason = (
                f"Phase {phase} failed quality gate after {state.retry_count} retries. "
                f"Last score: {result.total_score}. Feedback: {result.feedback}"
            )
            await self._escalate(run_id, reason)

    async def stop_pipeline(self, run_id: UUID, reason: str) -> None:
        """
        Forcibly stop a pipeline run, marking both the run and state as FAILED.
        """
        logger.info("pipeline_stopping", run_id=str(run_id), reason=reason)

        async with self._session_factory() as session:
            await session.execute(
                update(FactoryRun)
                .where(FactoryRun.id == run_id)
                .values(
                    status=RunStatus.FAILED.value,
                    error_message=reason,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(
                update(OrchestrationState)
                .where(OrchestrationState.run_id == run_id)
                .values(
                    phase_status=PhaseStatus.FAILED.value,
                    escalation_reason=reason,
                )
            )

        logger.info("pipeline_stopped", run_id=str(run_id))

    async def get_orchestration_state(
        self, run_id: UUID
    ) -> OrchestrationState | None:
        """Return the current OrchestrationState for a run, or None."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(OrchestrationState).where(
                    OrchestrationState.run_id == run_id
                )
            )
            return result.scalar_one_or_none()

    # ── Private helpers ─────────────────────────────────────────────────────

    async def _transition_phase(
        self, run_id: UUID, target: PhaseStatus
    ) -> None:
        """Validate and apply a phase status transition, persisting to DB."""
        state = await self.get_orchestration_state(run_id)
        if state is None:
            raise OrchestrationError(f"No state for run {run_id}")

        current = PhaseStatus(state.phase_status)
        if not validate_transition(current, target):
            raise OrchestrationError(
                f"Invalid transition for run {run_id} phase {state.current_phase}: "
                f"{current.value} -> {target.value}"
            )

        async with self._session_factory() as session:
            await session.execute(
                update(OrchestrationState)
                .where(OrchestrationState.run_id == run_id)
                .values(phase_status=target.value)
            )

        logger.debug(
            "phase_transition",
            run_id=str(run_id),
            phase=state.current_phase,
            from_status=current.value,
            to_status=target.value,
        )

    async def _move_to_next_phase(self, run_id: UUID, completed_phase: int) -> None:
        """
        After a phase PASSES, move to the next phase (PENDING) or complete the run.
        """
        next_phase = completed_phase + 1

        if next_phase >= MAX_PHASES:
            # All phases complete — mark the run as completed
            async with self._session_factory() as session:
                await session.execute(
                    update(FactoryRun)
                    .where(FactoryRun.id == run_id)
                    .values(
                        status=RunStatus.COMPLETED.value,
                        completed_at=datetime.now(timezone.utc),
                        current_phase=completed_phase,
                    )
                )
                await session.execute(
                    update(OrchestrationState)
                    .where(OrchestrationState.run_id == run_id)
                    .values(
                        phase_status=PhaseStatus.PASSED.value,
                        current_phase=completed_phase,
                    )
                )
            logger.info("pipeline_completed", run_id=str(run_id), final_phase=completed_phase)
            return

        # Advance to the next phase
        async with self._session_factory() as session:
            await session.execute(
                update(OrchestrationState)
                .where(OrchestrationState.run_id == run_id)
                .values(
                    current_phase=next_phase,
                    phase_status=PhaseStatus.PENDING.value,
                    retry_count=0,
                )
            )
            await session.execute(
                update(FactoryRun)
                .where(FactoryRun.id == run_id)
                .values(current_phase=next_phase)
            )

        logger.info(
            "phase_advanced",
            run_id=str(run_id),
            from_phase=completed_phase,
            to_phase=next_phase,
            phase_name=PHASE_NAMES.get(next_phase, f"Phase {next_phase}"),
        )

        # Auto-kick-off the next phase if it is ungated
        if next_phase in UNGATED_PHASES:
            await self.advance_phase(run_id)

    async def _escalate(self, run_id: UUID, reason: str) -> None:
        """Escalate the run after exhausting gate retries."""
        logger.warning("pipeline_escalated", run_id=str(run_id), reason=reason)

        async with self._session_factory() as session:
            await session.execute(
                update(OrchestrationState)
                .where(OrchestrationState.run_id == run_id)
                .values(
                    phase_status=PhaseStatus.ESCALATED.value,
                    escalation_reason=reason,
                )
            )
            await session.execute(
                update(FactoryRun)
                .where(FactoryRun.id == run_id)
                .values(
                    status=RunStatus.ESCALATED.value,
                    error_message=reason,
                )
            )
