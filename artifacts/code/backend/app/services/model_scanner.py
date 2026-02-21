"""Model scanner — probes all providers, grades models, suggests configuration."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import structlog

from app.providers.base import HealthStatus, ModelInfo, ProviderAdapter

if TYPE_CHECKING:
    from app.providers.registry import ProviderRegistry

logger = structlog.get_logger()

# ── DTOs ────────────────────────────────────────────────────────────────────


@dataclass
class ProbeResult:
    provider: str
    model: str
    success: bool
    latency_ms: int
    error: str | None = None


@dataclass
class ModelGrade:
    provider: str
    model: str
    overall_score: float
    quality_score: float
    availability_score: float
    rate_limit_score: float
    context_score: float
    speed_score: float
    is_available: bool
    context_window: int
    capability_tags: list[str] = field(default_factory=list)


@dataclass
class RoleRecommendation:
    role: str
    provider: str
    model: str
    score: float
    reason: str


@dataclass
class SuggestedConfig:
    recommendations: list[RoleRecommendation]
    overall_viability: int          # 0-100
    viability_description: str
    scan_duration_seconds: float
    providers_scanned: int
    providers_healthy: int
    cached: bool
    cache_age_minutes: float


@dataclass
class ScanResult:
    grades: list[ModelGrade]
    suggestion: SuggestedConfig
    timestamp: datetime
    cached: bool


# ── Scanner roles to grade for ───────────────────────────────────────────────

_ROLES = [
    "orchestrator",
    "requirements",
    "architect",
    "implementer",
    "tester",
    "reviewer",
    "security",
]

# Simple capability requirements per role (tags that boost the score)
_ROLE_PREFERRED_TAGS: dict[str, list[str]] = {
    "orchestrator": ["reasoning", "instruction-following"],
    "requirements": ["long-context", "reasoning"],
    "architect": ["reasoning", "code"],
    "implementer": ["code", "fast"],
    "tester": ["reasoning", "code"],
    "reviewer": ["reasoning", "long-context"],
    "security": ["reasoning", "code"],
}

# Context window thresholds (tokens)
_CTX_LARGE = 128_000
_CTX_MEDIUM = 32_000
_CTX_SMALL = 8_000

# Speed thresholds (ms) — lower is better
_SPEED_FAST = 1_000
_SPEED_OK = 3_000
_SPEED_SLOW = 8_000

# Cache TTL (minutes)
_CACHE_TTL_MINUTES = 30


class ModelScanner:
    """
    Scans all registered providers, probes their models, grades each model,
    and produces configuration recommendations.

    Grades are computed as a weighted composite:
        overall = 0.4*quality + 0.2*availability + 0.2*rate_limit + 0.1*context + 0.1*speed
    """

    def __init__(self, registry: "ProviderRegistry") -> None:
        self._registry = registry
        self._cache: ScanResult | None = None
        self._cache_timestamp: float = 0.0

    async def scan_all(self, force: bool = False) -> ScanResult:
        """
        Scan every registered provider and grade all their models.

        Args:
            force: Bypass the in-memory cache even if it is still fresh.

        Returns:
            ScanResult with grades and configuration suggestions.
        """
        now = time.time()
        cache_age_s = now - self._cache_timestamp
        cache_age_min = cache_age_s / 60.0

        if not force and self._cache is not None and cache_age_min < _CACHE_TTL_MINUTES:
            logger.info("model_scan_cache_hit", age_minutes=round(cache_age_min, 1))
            cached = ScanResult(
                grades=self._cache.grades,
                suggestion=SuggestedConfig(
                    **{
                        **self._cache.suggestion.__dict__,
                        "cached": True,
                        "cache_age_minutes": cache_age_min,
                    }
                ),
                timestamp=self._cache.timestamp,
                cached=True,
            )
            return cached

        scan_start = time.time()
        logger.info("model_scan_started", force=force)

        providers = self._registry.list_providers()
        providers_scanned = len(providers)
        providers_healthy = 0
        all_grades: list[ModelGrade] = []

        for info in providers:
            try:
                adapter: ProviderAdapter = self._registry.get_provider(info.name)
                health: HealthStatus = await adapter.check_health()
                if health.is_healthy:
                    providers_healthy += 1
                models: list[ModelInfo] = await adapter.list_models()
            except Exception as exc:
                logger.warning(
                    "scan_provider_failed",
                    provider=info.name,
                    error=str(exc),
                )
                continue

            # Probe and grade each model (up to 5 per provider to limit time)
            for model_info in models[:5]:
                probe = await self.probe_model(info.name, model_info.name)
                grade = self.grade_model(model_info, probe)
                all_grades.append(grade)

        scan_duration = time.time() - scan_start
        suggestion = self.suggest_configuration(all_grades)
        suggestion.scan_duration_seconds = scan_duration
        suggestion.providers_scanned = providers_scanned
        suggestion.providers_healthy = providers_healthy
        suggestion.cached = False
        suggestion.cache_age_minutes = 0.0

        # Compute overall viability
        healthy_providers = max(providers_healthy, 0)
        if healthy_providers == 0:
            viability = 0
            viability_desc = "No healthy providers available. The factory cannot run."
        elif healthy_providers == 1:
            viability = 40
            viability_desc = "Only 1 healthy provider. Limited cross-provider verification."
        elif healthy_providers < 4:
            viability = 70
            viability_desc = f"{healthy_providers} providers healthy. Basic pipeline viable."
        else:
            viability = 100
            viability_desc = (
                f"Excellent: {healthy_providers} providers healthy. "
                "Full cross-provider verification possible."
            )
        suggestion.overall_viability = viability
        suggestion.viability_description = viability_desc

        result = ScanResult(
            grades=all_grades,
            suggestion=suggestion,
            timestamp=datetime.utcnow(),
            cached=False,
        )

        # Update cache
        self._cache = result
        self._cache_timestamp = time.time()

        logger.info(
            "model_scan_complete",
            grades=len(all_grades),
            providers_scanned=providers_scanned,
            providers_healthy=providers_healthy,
            duration_s=round(scan_duration, 2),
        )
        return result

    async def probe_model(self, provider: str, model: str) -> ProbeResult:
        """
        Send a minimal test completion to *model* on *provider* and measure latency.

        Returns:
            ProbeResult with success/failure and latency information.
        """
        messages = [{"role": "user", "content": "Reply with the single word: OK"}]
        start = time.time()
        try:
            adapter: ProviderAdapter = self._registry.get_provider(provider)
            response = await adapter.chat_completion(
                model,
                messages,
                temperature=0.0,
                max_tokens=5,
                timeout=15.0,
            )
            latency_ms = int((time.time() - start) * 1000)
            return ProbeResult(
                provider=provider,
                model=model,
                success=True,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = int((time.time() - start) * 1000)
            logger.debug(
                "probe_failed",
                provider=provider,
                model=model,
                error=str(exc),
            )
            return ProbeResult(
                provider=provider,
                model=model,
                success=False,
                latency_ms=latency_ms,
                error=str(exc),
            )

    def grade_model(self, model_info: ModelInfo, probe_result: ProbeResult) -> ModelGrade:
        """
        Compute a composite grade for a model from its ModelInfo and ProbeResult.

        Scoring (0.0 – 1.0 per dimension):
            quality      (0.4 weight): heuristic from cost/context/tools
            availability (0.2 weight): probe success
            rate_limit   (0.2 weight): based on is_free flag
            context      (0.1 weight): context window size bucket
            speed        (0.1 weight): probe latency

        Returns:
            ModelGrade with overall_score and per-dimension scores.
        """
        # --- availability (binary from probe) ---
        availability_score = 1.0 if probe_result.success else 0.0

        # --- speed ---
        if probe_result.latency_ms <= _SPEED_FAST:
            speed_score = 1.0
        elif probe_result.latency_ms <= _SPEED_OK:
            speed_score = 0.7
        elif probe_result.latency_ms <= _SPEED_SLOW:
            speed_score = 0.4
        else:
            speed_score = 0.1

        # --- context window ---
        if model_info.context_window >= _CTX_LARGE:
            context_score = 1.0
        elif model_info.context_window >= _CTX_MEDIUM:
            context_score = 0.6
        elif model_info.context_window >= _CTX_SMALL:
            context_score = 0.3
        else:
            context_score = 0.1

        # --- rate limit (free = better for high-volume pipelines) ---
        rate_limit_score = 1.0 if model_info.is_free else 0.5

        # --- quality heuristic ---
        quality_score = 0.5  # base
        if model_info.supports_tools:
            quality_score += 0.2
        if model_info.supports_vision:
            quality_score += 0.1
        # Lower cost hints at free/high-quality free tier
        if model_info.is_free:
            quality_score += 0.2
        quality_score = min(quality_score, 1.0)

        # --- weighted composite ---
        overall = (
            0.4 * quality_score
            + 0.2 * availability_score
            + 0.2 * rate_limit_score
            + 0.1 * context_score
            + 0.1 * speed_score
        )

        return ModelGrade(
            provider=model_info.provider,
            model=model_info.name,
            overall_score=round(overall, 4),
            quality_score=round(quality_score, 4),
            availability_score=round(availability_score, 4),
            rate_limit_score=round(rate_limit_score, 4),
            context_score=round(context_score, 4),
            speed_score=round(speed_score, 4),
            is_available=probe_result.success,
            context_window=model_info.context_window,
            capability_tags=list(model_info.capability_tags),
        )

    def suggest_configuration(
        self, grades: list[ModelGrade]
    ) -> SuggestedConfig:
        """
        Derive per-role model recommendations from the grade list.

        Only available (probe succeeded) models are considered.
        The highest-scoring model per role is selected, with a preference for
        models whose capability_tags overlap with the role's preferred tags.

        Returns:
            SuggestedConfig with one RoleRecommendation per role and viability stats.
        """
        available = [g for g in grades if g.is_available]
        recommendations: list[RoleRecommendation] = []

        for role in _ROLES:
            preferred_tags = set(_ROLE_PREFERRED_TAGS.get(role, []))

            def _score(g: ModelGrade) -> float:
                tag_bonus = 0.05 * len(preferred_tags & set(g.capability_tags))
                return g.overall_score + tag_bonus

            if not available:
                continue

            best = max(available, key=_score)
            reason_parts = [
                f"overall_score={best.overall_score:.2f}",
                f"availability={best.availability_score:.2f}",
                f"context={best.context_window // 1000}k",
            ]
            if preferred_tags & set(best.capability_tags):
                reason_parts.append(
                    "has preferred tags: "
                    + ", ".join(preferred_tags & set(best.capability_tags))
                )

            recommendations.append(
                RoleRecommendation(
                    role=role,
                    provider=best.provider,
                    model=best.model,
                    score=round(_score(best), 4),
                    reason="; ".join(reason_parts),
                )
            )

        return SuggestedConfig(
            recommendations=recommendations,
            overall_viability=0,       # filled by caller
            viability_description="",  # filled by caller
            scan_duration_seconds=0.0, # filled by caller
            providers_scanned=0,       # filled by caller
            providers_healthy=0,       # filled by caller
            cached=False,
            cache_age_minutes=0.0,
        )
