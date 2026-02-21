"""Unit tests for provider fallback chain and circuit breaker (black-box)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.base import CompletionResponse
from app.providers.fallback_chain import (
    AllProvidersExhaustedError,
    CircuitBreaker,
    FallbackChain,
    PaidPermissionRequiredError,
)


def _make_adapter(name: str, is_free: bool = True, response: CompletionResponse | None = None, error: Exception | None = None):
    """Create a mock provider adapter."""
    adapter = AsyncMock()
    adapter.name = name
    adapter.display_name = name.title()
    adapter.is_free = is_free
    if error:
        adapter.chat_completion = AsyncMock(side_effect=error)
    elif response:
        adapter.chat_completion = AsyncMock(return_value=response)
    else:
        adapter.chat_completion = AsyncMock(return_value=CompletionResponse(
            content="test response",
            model=f"{name}-model",
            provider=name,
            tokens_input=10,
            tokens_output=20,
            cost=0.0,
            latency_ms=100,
            finish_reason="stop",
        ))
    return adapter


def _make_response(provider: str = "test", cost: float = 0.0) -> CompletionResponse:
    return CompletionResponse(
        content="response",
        model=f"{provider}-model",
        provider=provider,
        tokens_input=10,
        tokens_output=20,
        cost=cost,
        latency_ms=100,
        finish_reason="stop",
    )


class TestFallbackChainSuccess:
    @pytest.mark.asyncio
    async def test_primary_succeeds(self):
        adapter = _make_adapter("groq")
        chain = FallbackChain([("groq", "llama-70b", adapter)])
        result = await chain.execute("implementer", [{"role": "user", "content": "test"}])
        assert result.provider == "groq"
        adapter.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_primary_fails_secondary_succeeds(self):
        adapter1 = _make_adapter("groq", error=RuntimeError("rate limited"))
        adapter2 = _make_adapter("nvidia")
        chain = FallbackChain([
            ("groq", "llama-70b", adapter1),
            ("nvidia", "nemotron", adapter2),
        ])
        result = await chain.execute("implementer", [{"role": "user", "content": "test"}])
        assert result.provider == "nvidia"
        adapter1.chat_completion.assert_called_once()
        adapter2.chat_completion.assert_called_once()


class TestFallbackChainFailure:
    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        adapter1 = _make_adapter("groq", error=RuntimeError("down"))
        adapter2 = _make_adapter("nvidia", error=RuntimeError("down"))
        chain = FallbackChain([
            ("groq", "llama-70b", adapter1),
            ("nvidia", "nemotron", adapter2),
        ])
        with pytest.raises(AllProvidersExhaustedError):
            await chain.execute("implementer", [{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_paid_provider_raises_when_free_only(self):
        paid_response = _make_response("openai", cost=0.05)
        adapter = _make_adapter("openai", is_free=False, response=paid_response)
        # When free_only=True, paid adapters should be skipped
        chain = FallbackChain([("openai", "gpt-4", adapter)])
        with pytest.raises(AllProvidersExhaustedError):
            await chain.execute("implementer", [{"role": "user", "content": "test"}], free_only=True)


class TestCircuitBreaker:
    def test_initially_closed(self):
        cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_seconds=300)
        assert cb.is_open("groq") is False

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_seconds=300)
        for _ in range(5):
            cb.record_failure("groq")
        assert cb.is_open("groq") is True

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_seconds=300)
        for _ in range(4):
            cb.record_failure("groq")
        assert cb.is_open("groq") is False

    def test_success_resets_failures(self):
        cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_seconds=300)
        for _ in range(4):
            cb.record_failure("groq")
        cb.record_success("groq")
        # After success, should need 5 new failures
        assert cb.is_open("groq") is False

    def test_half_open_after_recovery(self):
        cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_seconds=1)
        for _ in range(5):
            cb.record_failure("groq")
        assert cb.is_open("groq") is True
        # Wait for recovery
        time.sleep(1.1)
        assert cb.is_open("groq") is False  # half-open

    @pytest.mark.asyncio
    async def test_open_circuit_skips_provider(self):
        cb = CircuitBreaker(failure_threshold=2, window_seconds=60, recovery_seconds=300)
        for _ in range(2):
            cb.record_failure("groq")

        adapter1 = _make_adapter("groq")
        adapter2 = _make_adapter("nvidia")
        chain = FallbackChain(
            [("groq", "llama", adapter1), ("nvidia", "nemotron", adapter2)],
            circuit_breaker=cb,
        )
        result = await chain.execute("implementer", [{"role": "user", "content": "test"}])
        assert result.provider == "nvidia"
        # groq should have been skipped (circuit open)
        adapter1.chat_completion.assert_not_called()

    def test_per_provider_isolation(self):
        cb = CircuitBreaker(failure_threshold=3, window_seconds=60, recovery_seconds=300)
        for _ in range(3):
            cb.record_failure("groq")
        assert cb.is_open("groq") is True
        assert cb.is_open("nvidia") is False
