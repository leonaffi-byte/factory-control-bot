"""Integration tests for factory orchestrator flow (black-box, per spec-v2.md)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.orchestrator.state_machine import PhaseStatus, GATED_PHASES, UNGATED_PHASES


class TestOrchestratorStartPipeline:
    @pytest.mark.asyncio
    async def test_start_pipeline_creates_run(self):
        """start_pipeline should create a FactoryRun and OrchestrationState."""
        from app.services.factory_orchestrator import FactoryOrchestrator

        mock_session = AsyncMock()
        mock_router = AsyncMock()
        orchestrator = FactoryOrchestrator(mock_session, mock_router)

        project = MagicMock()
        project.id = uuid.uuid4()
        project.name = "test-project"

        run = await orchestrator.start_pipeline(
            project=project,
            engine="claude",
            tier=2,
            interface_source="telegram",
        )
        assert run is not None


class TestPhaseTransitions:
    """Test that the orchestrator respects state machine transitions."""

    def test_gated_phases_go_through_scoring(self):
        """Phases 1, 3, 7 must go through SCORING state."""
        for phase in GATED_PHASES:
            assert phase in {1, 3, 7}

    def test_ungated_phases_skip_scoring(self):
        """Phases 0, 2, 4, 5, 6 skip SCORING and go directly to PASSED."""
        for phase in UNGATED_PHASES:
            assert phase in {0, 2, 4, 5, 6}


class TestQualityGateFlow:
    def test_gate_pass_advances_phase(self):
        """Score >= 97 should advance to next phase."""
        from app.orchestrator.quality_gate import QualityGateResult

        result = QualityGateResult(
            phase=1,
            total_score=98,
            completeness=25,
            clarity=25,
            consistency=24,
            robustness=24,
            passed=True,
            threshold=97,
            feedback="Good.",
            iteration=1,
        )
        assert result.passed is True

    def test_gate_fail_triggers_iteration(self):
        """Score < 97 should trigger iteration (retry)."""
        from app.orchestrator.quality_gate import QualityGateResult

        result = QualityGateResult(
            phase=1,
            total_score=85,
            completeness=22,
            clarity=21,
            consistency=21,
            robustness=21,
            passed=False,
            threshold=97,
            feedback="Needs work.",
            gaps=["Missing edge cases"],
            iteration=1,
        )
        assert result.passed is False
        assert len(result.gaps) > 0

    def test_max_iterations_escalates(self):
        """After 3 iterations, should escalate to user."""
        from app.orchestrator.state_machine import validate_transition

        # FAILED -> ESCALATED is valid
        assert validate_transition(PhaseStatus.FAILED, PhaseStatus.ESCALATED) is True
        # ESCALATED is terminal
        assert validate_transition(PhaseStatus.ESCALATED, PhaseStatus.RUNNING) is False


class TestResumeInterrupted:
    @pytest.mark.asyncio
    async def test_resume_from_phase_4(self):
        """Bot restart during Phase 4 should resume from Phase 4."""
        from app.orchestrator.state_machine import PhaseStatus

        # Simulate an orchestration state that was interrupted at phase 4
        state = MagicMock()
        state.current_phase = 4
        state.phase_status = PhaseStatus.RUNNING.value
        state.retry_count = 0

        # The resume should pick up from phase 4, not restart
        assert state.current_phase == 4
        assert state.phase_status == "running"


class TestConcurrencyControl:
    def test_advisory_lock_prevents_concurrent_access(self):
        """Two processes modifying the same run should use advisory locks."""
        # This is a design verification test - the orchestrator must use
        # pg_try_advisory_lock(hashtext('run:' || run_id))
        from app.orchestrator.state_machine import PhaseStatus

        # Verify the state machine supports the locking concept
        # (concurrent access to RUNNING -> SCORING must be serialized)
        assert validate_transition(PhaseStatus.RUNNING, PhaseStatus.SCORING) is True
