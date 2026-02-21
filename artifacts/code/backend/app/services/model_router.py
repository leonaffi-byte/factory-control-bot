"""Model router — routes completion requests through providers with fallback."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.providers.base import CompletionResponse, ProviderAdapter
from app.providers.fallback_chain import (
    AllProvidersExhaustedError,
    FallbackChain,
)

if TYPE_CHECKING:
    from app.providers.rate_limiter import ProviderRateLimiter
    from app.providers.registry import ProviderRegistry

logger = structlog.get_logger()

# ── Tier-based role -> (provider, model) mapping ────────────────────────────

# Tier 1: simple projects
_TIER1_ASSIGNMENTS: dict[str, tuple[str, str]] = {
    "orchestrator": ("groq", "llama-3.3-70b-versatile"),
    "requirements": ("google_ai", "gemini-2.5-flash"),
    "architect": ("groq", "llama-3.3-70b-versatile"),
    "implementer": ("groq", "llama-3.3-70b-versatile"),
    "tester": ("openrouter", "qwen/qwen3-235b-a22b"),
    "reviewer": ("openrouter", "openai/gpt-5.2"),
    "security": ("google_ai", "gemini-2.5-flash"),
}

# Tier 2: medium projects
_TIER2_ASSIGNMENTS: dict[str, tuple[str, str]] = {
    "orchestrator": ("groq", "llama-3.3-70b-versatile"),
    "requirements": ("google_ai", "gemini-3-pro"),
    "architect": ("groq", "llama-3.3-70b-versatile"),
    "implementer": ("groq", "llama-3.3-70b-versatile"),
    "tester": ("openrouter", "openai/gpt-5.2"),
    "reviewer": ("openrouter", "openai/o3"),
    "security": ("google_ai", "gemini-3-pro"),
}

# Tier 3: complex projects
_TIER3_ASSIGNMENTS: dict[str, tuple[str, str]] = {
    "orchestrator": ("groq", "llama-3.3-70b-versatile"),
    "requirements": ("google_ai", "gemini-3-pro"),
    "architect": ("groq", "llama-3.3-70b-versatile"),
    "implementer": ("groq", "llama-3.3-70b-versatile"),
    "tester": ("openrouter", "openai/gpt-5.2"),
    "reviewer": ("openrouter", "openai/o3"),
    "security": ("google_ai", "gemini-3-pro"),
    "security_second": ("openrouter", "zhipu/glm-5"),
    "full_context": ("openrouter", "moonshot/kimi-2.5"),
    "research": ("openrouter", "perplexity/sonar-deep-research"),
}

_TIER_MAP: dict[int, dict[str, tuple[str, str]]] = {
    1: _TIER1_ASSIGNMENTS,
    2: _TIER2_ASSIGNMENTS,
    3: _TIER3_ASSIGNMENTS,
}

# Ordered fallback providers used when the preferred provider is unavailable.
# Sorted by typical quality/reliability.
_FALLBACK_ORDER: list[tuple[str, str]] = [
    ("cerebras", "llama-3.3-70b"),
    ("groq", "llama-3.3-70b-versatile"),
    ("nvidia", "meta/llama-3.3-70b-instruct"),
    ("sambanova", "Meta-Llama-3.3-70B-Instruct"),
    ("together", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    ("openrouter", "meta-llama/llama-3.3-70b-instruct"),
]


class ModelRouter:
    """
    Routes model completion requests through available providers.

    Uses a FallbackChain for waterfall routing and circuit-breaking.
    Can also route to a specific provider/model directly.
    """

    def __init__(
        self,
        registry: "ProviderRegistry",
        rate_limiter: "ProviderRateLimiter",
    ) -> None:
        self._registry = registry
        self._rate_limiter = rate_limiter

    async def route(
        self,
        role: str,
        messages: list[dict],
        *,
        free_only: bool = True,
        preferred_provider: str | None = None,
        tier: int = 2,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 120.0,
    ) -> CompletionResponse:
        """
        Route a completion request for *role* through the best available provider.

        Builds a FallbackChain starting from the preferred or tier-assigned provider
        and falling back through _FALLBACK_ORDER.

        Args:
            role: Agent role key (e.g. "implementer", "tester").
            messages: OpenAI-style message list.
            free_only: Restrict to providers marked as free.
            preferred_provider: Override the tier-default provider name.
            tier: Complexity tier for model assignment lookup.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.
            timeout: Per-request timeout in seconds.

        Returns:
            CompletionResponse from the first successful provider.

        Raises:
            AllProvidersExhaustedError: If every provider in the chain failed.
        """
        chain_entries = self._build_chain(
            role=role,
            tier=tier,
            preferred_provider=preferred_provider,
            free_only=free_only,
        )

        if not chain_entries:
            raise AllProvidersExhaustedError(
                f"No suitable providers available for role={role} "
                f"(free_only={free_only})"
            )

        chain = FallbackChain(providers=chain_entries)
        response = await chain.execute(
            role=role,
            messages=messages,
            free_only=free_only,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

        # Track rate limit usage
        self._rate_limiter.record_request(
            provider_name=response.provider,
            model_name=response.model,
            tokens=response.tokens_input + response.tokens_output,
        )

        logger.info(
            "model_routed",
            role=role,
            provider=response.provider,
            model=response.model,
            tokens_in=response.tokens_input,
            tokens_out=response.tokens_output,
            cost=response.cost,
            latency_ms=response.latency_ms,
        )
        return response

    async def route_to_specific(
        self,
        provider: str,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 120.0,
    ) -> CompletionResponse:
        """
        Route directly to a specific provider and model, bypassing the fallback chain.

        Args:
            provider: Registered provider name (e.g. "groq", "google_ai").
            model: Model identifier as expected by the provider adapter.
            messages: OpenAI-style message list.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.
            timeout: Per-request timeout in seconds.

        Returns:
            CompletionResponse from the provider.

        Raises:
            KeyError: If the provider is not registered.
        """
        adapter: ProviderAdapter = self._registry.get_provider(provider)
        response = await adapter.chat_completion(
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

        self._rate_limiter.record_request(
            provider_name=provider,
            model_name=model,
            tokens=response.tokens_input + response.tokens_output,
        )

        logger.info(
            "model_routed_direct",
            provider=provider,
            model=model,
            tokens_in=response.tokens_input,
            tokens_out=response.tokens_output,
            cost=response.cost,
            latency_ms=response.latency_ms,
        )
        return response

    def get_model_for_role(self, role: str, tier: int) -> tuple[str, str]:
        """
        Return the (provider, model) tuple assigned to *role* for the given *tier*.

        Falls back to tier 2 if the requested tier is not in the mapping.

        Args:
            role: Agent role key.
            tier: Complexity tier (1, 2, or 3).

        Returns:
            Tuple of (provider_name, model_name).

        Raises:
            KeyError: If *role* is not defined for the given tier.
        """
        assignments = _TIER_MAP.get(tier) or _TIER_MAP[2]
        if role not in assignments:
            # Graceful fallback to tier 2
            assignments = _TIER_MAP[2]
        if role not in assignments:
            raise KeyError(f"Role '{role}' is not defined in the model assignment table")
        return assignments[role]

    # ── Private helpers ─────────────────────────────────────────────────────

    def _build_chain(
        self,
        role: str,
        tier: int,
        preferred_provider: str | None,
        free_only: bool,
    ) -> list[tuple[str, str, ProviderAdapter]]:
        """
        Build an ordered list of (provider_name, model_name, adapter) for the chain.

        Starts with the tier-preferred assignment, then appends the global fallback list.
        Deduplicates and skips providers not registered or not available.
        """
        chain: list[tuple[str, str, ProviderAdapter]] = []
        seen_providers: set[str] = set()

        # 1. Preferred provider override
        if preferred_provider and preferred_provider in self._registry:
            assignments = _TIER_MAP.get(tier, _TIER_MAP[2])
            _, model = assignments.get(role, ("", "llama-3.3-70b-versatile"))
            try:
                adapter = self._registry.get_provider(preferred_provider)
                chain.append((preferred_provider, model, adapter))
                seen_providers.add(preferred_provider)
            except KeyError:
                logger.warning(
                    "preferred_provider_not_registered",
                    provider=preferred_provider,
                )

        # 2. Tier-assigned provider
        try:
            tier_provider, tier_model = self.get_model_for_role(role, tier)
            if tier_provider not in seen_providers and tier_provider in self._registry:
                adapter = self._registry.get_provider(tier_provider)
                if not free_only or adapter.is_free:
                    chain.append((tier_provider, tier_model, adapter))
                    seen_providers.add(tier_provider)
        except KeyError:
            logger.warning("role_not_in_tier_assignments", role=role, tier=tier)

        # 3. Global fallback list
        for fb_provider, fb_model in _FALLBACK_ORDER:
            if fb_provider in seen_providers:
                continue
            if fb_provider not in self._registry:
                continue
            try:
                adapter = self._registry.get_provider(fb_provider)
                if free_only and not adapter.is_free:
                    continue
                if not self._rate_limiter.check_allowed(fb_provider):
                    logger.info("provider_rate_limited_skipped", provider=fb_provider)
                    continue
                chain.append((fb_provider, fb_model, adapter))
                seen_providers.add(fb_provider)
            except KeyError:
                continue

        return chain
