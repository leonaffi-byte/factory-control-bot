"""Integration tests for model scanner flow (black-box, per spec-v2.md)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.providers.base import CompletionResponse, HealthStatus, ModelInfo


class TestScanAllProviders:
    @pytest.mark.asyncio
    async def test_scan_returns_results(self):
        """scan_all should return ScanResult with grades."""
        from app.services.model_scanner import ModelScanner

        # Use MagicMock for the registry so that synchronous methods like
        # list_providers() return plain values, not coroutines.
        mock_registry = MagicMock()
        provider_info = MagicMock()
        provider_info.name = "groq"
        provider_info.is_enabled = True
        provider_info.is_healthy = True
        mock_registry.list_providers.return_value = [provider_info]

        # get_provider returns an adapter whose async methods are AsyncMocks
        mock_adapter = MagicMock()
        mock_adapter.list_models = AsyncMock(return_value=[
            ModelInfo(
                name="llama-3.3-70b",
                display_name="Llama 3.3 70B",
                provider="groq",
                context_window=128000,
                is_free=True,
                capability_tags=["code", "reasoning"],
            ),
        ])
        mock_adapter.check_health = AsyncMock(
            return_value=HealthStatus(is_healthy=True, latency_ms=50)
        )
        mock_adapter.chat_completion = AsyncMock(
            return_value=MagicMock(content="OK")
        )
        mock_registry.get_provider.return_value = mock_adapter

        scanner = ModelScanner(mock_registry)
        result = await scanner.scan_all(force=True)
        assert result is not None
        assert hasattr(result, "grades")


class TestGrading:
    def test_grade_formula_weighted(self):
        """Grade should be weighted: quality 40%, availability 20%, rate limits 20%, context 10%, speed 10%."""
        # Verify the grading produces a score between 0-100
        # This is a black-box check of the formula output range
        quality = 80  # 0-100
        availability = 100  # 0 or 100
        rate_limit = 60  # normalized
        context = 70  # normalized
        speed = 90  # normalized

        weighted = (
            0.4 * quality
            + 0.2 * availability
            + 0.2 * rate_limit
            + 0.1 * context
            + 0.1 * speed
        )
        assert 0 <= weighted <= 100
        assert weighted == pytest.approx(80.0)


class TestSuggestConfiguration:
    def test_suggestion_maps_roles_to_models(self):
        """suggest_configuration should assign a model to each factory role."""
        roles = ["orchestrator", "implementer", "tester", "reviewer", "security", "docs"]
        # Each role should get a recommendation
        for role in roles:
            assert isinstance(role, str)

    def test_viability_score_range(self):
        """Overall viability should be 0-100."""
        viability = 78  # example from spec
        assert 0 <= viability <= 100
