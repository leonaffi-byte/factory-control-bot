"""Waterfall fallback chain for provider routing."""
from __future__ import annotations

import time

import structlog

from app.providers.base import CompletionResponse, ProviderAdapter

logger = structlog.get_logger()


class AllProvidersExhaustedError(Exception):
    pass


class PaidPermissionRequiredError(Exception):
    def __init__(self, provider: str, model: str, estimated_cost: float) -> None:
        self.provider = provider
        self.model = model
        self.estimated_cost = estimated_cost
        super().__init__(
            f"Paid permission required: {provider}/{model} (~${estimated_cost})"
        )


class CircuitBreaker:
    """Per-provider circuit breaker: 5 failures in 60s -> OPEN for 5min."""

    def __init__(
        self,
        failure_threshold: int = 5,
        window_seconds: int = 60,
        recovery_seconds: int = 300,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.recovery_seconds = recovery_seconds
        self._failures: dict[str, list[float]] = {}  # provider -> [timestamps]
        self._open_until: dict[str, float] = {}  # provider -> timestamp

    def is_open(self, provider: str) -> bool:
        if provider in self._open_until:
            if time.time() < self._open_until[provider]:
                return True
            del self._open_until[provider]  # half-open
        return False

    def record_failure(self, provider: str) -> None:
        now = time.time()
        if provider not in self._failures:
            self._failures[provider] = []
        self._failures[provider].append(now)
        cutoff = now - self.window_seconds
        self._failures[provider] = [
            t for t in self._failures[provider] if t > cutoff
        ]
        if len(self._failures[provider]) >= self.failure_threshold:
            self._open_until[provider] = now + self.recovery_seconds
            logger.warning("circuit_breaker_opened", provider=provider)

    def record_success(self, provider: str) -> None:
        self._failures.pop(provider, None)
        self._open_until.pop(provider, None)


class FallbackChain:
    def __init__(
        self,
        providers: list[tuple[str, str, ProviderAdapter]],
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._chain = providers  # [(provider_name, model_name, adapter)]
        self._circuit_breaker = circuit_breaker or CircuitBreaker()

    async def execute(
        self,
        role: str,
        messages: list[dict],
        *,
        free_only: bool = True,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 120.0,
    ) -> CompletionResponse:
        errors: list[tuple[str, str, str]] = []
        for provider_name, model_name, adapter in self._chain:
            if free_only and not adapter.is_free:
                continue
            if self._circuit_breaker.is_open(provider_name):
                logger.info("provider_circuit_open", provider=provider_name)
                continue
            try:
                response = await adapter.chat_completion(
                    model_name,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                if response.cost > 0 and free_only:
                    raise PaidPermissionRequiredError(
                        provider_name, model_name, response.cost
                    )
                self._circuit_breaker.record_success(provider_name)
                return response
            except PaidPermissionRequiredError:
                raise
            except Exception as e:
                self._circuit_breaker.record_failure(provider_name)
                errors.append((provider_name, model_name, str(e)))
                logger.warning(
                    "provider_fallback",
                    provider=provider_name,
                    model=model_name,
                    error=str(e),
                )
                continue
        raise AllProvidersExhaustedError(
            f"All providers failed for role={role}: {errors}"
        )
