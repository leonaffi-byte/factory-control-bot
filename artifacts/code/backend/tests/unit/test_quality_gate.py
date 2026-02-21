"""Unit tests for quality gate scoring (black-box, per interfaces-v2.md)."""

from __future__ import annotations

import pytest

from app.orchestrator.quality_gate import QualityGateResult


class TestQualityGateResult:
    def test_passing_score(self):
        result = QualityGateResult(
            phase=1,
            total_score=98,
            completeness=25,
            clarity=25,
            consistency=24,
            robustness=24,
            passed=True,
            threshold=97,
            feedback="Excellent specification.",
            gaps=[],
            scored_by_model="gpt-5.2",
            scored_by_provider="openai",
            iteration=1,
        )
        assert result.passed is True
        assert result.total_score >= result.threshold
        assert result.total_score == 98
        assert result.gaps == []

    def test_failing_score(self):
        result = QualityGateResult(
            phase=3,
            total_score=72,
            completeness=20,
            clarity=18,
            consistency=17,
            robustness=17,
            passed=False,
            threshold=97,
            feedback="Many gaps found.",
            gaps=["Missing error handling", "No edge cases"],
            scored_by_model="gemini-3-pro",
            scored_by_provider="google",
            iteration=1,
        )
        assert result.passed is False
        assert result.total_score < result.threshold
        assert len(result.gaps) == 2

    def test_score_is_sum_of_dimensions(self):
        c, cl, co, r = 24, 25, 24, 25
        result = QualityGateResult(
            phase=1,
            total_score=c + cl + co + r,
            completeness=c,
            clarity=cl,
            consistency=co,
            robustness=r,
            passed=True,
            threshold=97,
            feedback="Good.",
            iteration=1,
        )
        assert result.total_score == result.completeness + result.clarity + result.consistency + result.robustness
        assert result.total_score == 98

    def test_perfect_score(self):
        result = QualityGateResult(
            phase=7,
            total_score=100,
            completeness=25,
            clarity=25,
            consistency=25,
            robustness=25,
            passed=True,
            threshold=97,
            feedback="Perfect.",
            iteration=2,
        )
        assert result.total_score == 100
        assert result.passed is True

    def test_threshold_boundary(self):
        """Score exactly at threshold should pass."""
        result = QualityGateResult(
            phase=1,
            total_score=97,
            completeness=25,
            clarity=24,
            consistency=24,
            robustness=24,
            passed=True,
            threshold=97,
            feedback="Just passed.",
            iteration=1,
        )
        assert result.total_score == result.threshold
        assert result.passed is True

    def test_iteration_tracking(self):
        for iteration in (1, 2, 3):
            result = QualityGateResult(
                phase=1,
                total_score=80,
                completeness=20,
                clarity=20,
                consistency=20,
                robustness=20,
                passed=False,
                threshold=97,
                feedback=f"Iteration {iteration}",
                iteration=iteration,
            )
            assert result.iteration == iteration

    def test_scored_by_fields(self):
        result = QualityGateResult(
            phase=3,
            total_score=100,
            completeness=25,
            clarity=25,
            consistency=25,
            robustness=25,
            passed=True,
            threshold=97,
            feedback="ok",
            scored_by_model="gpt-5.2",
            scored_by_provider="openai",
            iteration=1,
        )
        assert result.scored_by_model == "gpt-5.2"
        assert result.scored_by_provider == "openai"

    def test_dimension_ranges(self):
        """Each dimension is 0-25, total is 0-100."""
        result = QualityGateResult(
            phase=1,
            total_score=0,
            completeness=0,
            clarity=0,
            consistency=0,
            robustness=0,
            passed=False,
            threshold=97,
            feedback="Empty.",
            iteration=1,
        )
        assert result.total_score == 0
        assert all(
            getattr(result, dim) == 0
            for dim in ("completeness", "clarity", "consistency", "robustness")
        )
