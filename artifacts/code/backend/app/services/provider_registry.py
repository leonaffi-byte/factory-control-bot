"""Provider registry service — thin DI wrapper around ProviderRegistry."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.providers.base import HealthStatus, ProviderAdapter, ProviderInfo
from app.providers.registry import ProviderRegistry

if TYPE_CHECKING:
    from app.config import Settings

logger = structlog.get_logger()


class ProviderRegistryService:
    """
    Service-layer wrapper around the core ProviderRegistry.

    Provides the same interface as ProviderRegistry but slots neatly into the
    ServiceContainer dependency-injection pattern used throughout the project.
    All heavy lifting is delegated to the underlying ProviderRegistry instance.
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._registry = ProviderRegistry(settings=settings)
        self._initialized = False

    async def initialize(self) -> None:
        """
        Discover and register all providers that have API keys configured.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if self._initialized:
            return
        await self._registry.initialize()
        self._initialized = True
        logger.info(
            "provider_registry_service_initialized",
            provider_count=len(self._registry),
        )

    # ── Read-only delegation ─────────────────────────────────────────────────

    def list_providers(self, free_only: bool = False) -> list[ProviderInfo]:
        """
        Return ProviderInfo for all registered providers.

        Args:
            free_only: When True, only return providers marked as free.

        Returns:
            List of ProviderInfo dataclasses.
        """
        if free_only:
            return self._registry.get_free_providers()
        return self._registry.list_providers()

    def get_provider(self, name: str) -> ProviderAdapter:
        """
        Return the adapter for *name*.

        Raises:
            KeyError: If the provider is not registered.
        """
        return self._registry.get_provider(name)

    async def check_all_health(self) -> dict[str, HealthStatus]:
        """
        Run health checks on every registered provider and return results.

        Returns:
            Mapping of provider name -> HealthStatus.
        """
        results = await self._registry.check_health_all()
        logger.info(
            "health_check_complete",
            total=len(results),
            healthy=sum(1 for s in results.values() if s.is_healthy),
        )
        return results

    # ── Mutating delegation ──────────────────────────────────────────────────

    def enable_provider(self, name: str) -> None:
        """Re-enable a previously disabled provider."""
        self._registry.enable_provider(name)
        logger.info("provider_enabled", provider=name)

    def disable_provider(self, name: str) -> None:
        """Disable a provider so it is excluded from routing."""
        self._registry.disable_provider(name)
        logger.info("provider_disabled", provider=name)

    # ── Internal registry access (for model_router et al.) ──────────────────

    @property
    def registry(self) -> ProviderRegistry:
        """Expose the underlying ProviderRegistry for services that need it directly."""
        return self._registry

    def __contains__(self, name: str) -> bool:
        return name in self._registry

    def __len__(self) -> int:
        return len(self._registry)
