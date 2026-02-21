"""Provider registry managing all available LLM provider adapters."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import structlog

from app.providers.base import (
    HealthStatus,
    ProviderAdapter,
    ProviderConfig,
    ProviderInfo,
)

if TYPE_CHECKING:
    from app.config import Settings

logger = structlog.get_logger()

# Canonical provider configurations keyed by provider name
_PROVIDER_CONFIGS: list[ProviderConfig] = [
    ProviderConfig(
        name="groq",
        display_name="Groq",
        api_base_url="https://api.groq.com/openai/v1",
        api_key_env_var="groq_api_key",
        is_free=True,
        priority_score=90,
        openai_compatible=True,
        adapter_type="litellm",
        config={"litellm_prefix": "groq"},
    ),
    ProviderConfig(
        name="openrouter",
        display_name="OpenRouter",
        api_base_url="https://openrouter.ai/api/v1",
        api_key_env_var="openrouter_api_key",
        is_free=False,
        priority_score=60,
        openai_compatible=True,
        adapter_type="litellm",
        config={"litellm_prefix": "openrouter"},
    ),
    ProviderConfig(
        name="nvidia",
        display_name="NVIDIA NIM",
        api_base_url="https://integrate.api.nvidia.com/v1",
        api_key_env_var="nvidia_api_key",
        is_free=True,
        priority_score=80,
        openai_compatible=True,
        adapter_type="litellm",
        config={"litellm_prefix": "nvidia_nim"},
    ),
    ProviderConfig(
        name="together",
        display_name="Together AI",
        api_base_url="https://api.together.xyz/v1",
        api_key_env_var="together_api_key",
        is_free=False,
        priority_score=70,
        openai_compatible=True,
        adapter_type="litellm",
        config={"litellm_prefix": "together_ai"},
    ),
    ProviderConfig(
        name="cerebras",
        display_name="Cerebras Cloud",
        api_base_url="https://api.cerebras.ai/v1",
        api_key_env_var="cerebras_api_key",
        is_free=True,
        priority_score=85,
        openai_compatible=True,
        adapter_type="litellm",
        config={"litellm_prefix": "cerebras"},
    ),
    ProviderConfig(
        name="fireworks",
        display_name="Fireworks AI",
        api_base_url="https://api.fireworks.ai/inference/v1",
        api_key_env_var="fireworks_api_key",
        is_free=False,
        priority_score=65,
        openai_compatible=True,
        adapter_type="litellm",
        config={"litellm_prefix": "fireworks_ai"},
    ),
    ProviderConfig(
        name="mistral",
        display_name="Mistral AI",
        api_base_url="https://api.mistral.ai/v1",
        api_key_env_var="mistral_api_key",
        is_free=False,
        priority_score=70,
        openai_compatible=True,
        adapter_type="litellm",
        config={"litellm_prefix": "mistral"},
    ),
    ProviderConfig(
        name="google_ai",
        display_name="Google AI Studio",
        api_base_url=None,
        api_key_env_var="google_api_key",
        is_free=True,
        priority_score=88,
        openai_compatible=False,
        adapter_type="google_ai",
        config={},
    ),
    ProviderConfig(
        name="sambanova",
        display_name="SambaNova Cloud",
        api_base_url="https://api.sambanova.ai/v1",
        api_key_env_var="sambanova_api_key",
        is_free=True,
        priority_score=82,
        openai_compatible=True,
        adapter_type="sambanova",
        config={},
    ),
]


class ProviderRegistry:
    """Registry of all available LLM provider adapters.

    Discovers and registers providers based on available API keys from settings.
    Providers are keyed by their canonical name string.
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._adapters: dict[str, ProviderAdapter] = {}
        self._infos: dict[str, ProviderInfo] = {}
        self._health_cache: dict[str, HealthStatus] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Discover and register all providers that have API keys configured."""
        if self._initialized:
            return

        # Deferred imports to avoid circular deps at module load time
        from app.providers.litellm_adapter import LiteLLMAdapter
        from app.providers.google_ai_adapter import GoogleAIAdapter
        from app.providers.sambanova_adapter import SambaNovAdapter
        from app.providers.clink_adapter import ClinkAdapter

        for cfg in _PROVIDER_CONFIGS:
            api_key: str = getattr(self._settings, cfg.api_key_env_var, "")
            if not api_key:
                logger.debug(
                    "provider_skipped_no_key",
                    provider=cfg.name,
                    env_var=cfg.api_key_env_var,
                )
                continue

            try:
                adapter: ProviderAdapter
                if cfg.adapter_type == "litellm":
                    litellm_adapter = LiteLLMAdapter(cfg)
                    litellm_adapter.set_api_key(api_key)
                    adapter = litellm_adapter
                elif cfg.adapter_type == "google_ai":
                    adapter = GoogleAIAdapter(api_key=api_key)
                elif cfg.adapter_type == "sambanova":
                    adapter = SambaNovAdapter(api_key=api_key)
                else:
                    logger.warning("unknown_adapter_type", adapter_type=cfg.adapter_type)
                    continue

                self.register(cfg.name, adapter)
                logger.info("provider_registered", provider=cfg.name, free=cfg.is_free)

            except Exception as exc:
                logger.error(
                    "provider_init_failed",
                    provider=cfg.name,
                    error=str(exc),
                )

        # Always register clink (local CLI) as it needs no API key
        try:
            clink_adapter: ProviderAdapter = ClinkAdapter()
            self.register("clink", clink_adapter)
            logger.info("provider_registered", provider="clink", free=True)
        except Exception as exc:
            logger.warning("clink_init_failed", error=str(exc))

        self._initialized = True
        logger.info(
            "registry_initialized",
            total_providers=len(self._adapters),
            free_providers=len(self.get_free_providers()),
        )

    def register(self, name: str, adapter: ProviderAdapter) -> None:
        """Register a provider adapter under the given name."""
        self._adapters[name] = adapter
        # Determine model count synchronously via a placeholder (updated on health check)
        model_count = 0
        self._infos[name] = ProviderInfo(
            name=name,
            display_name=adapter.display_name,
            is_free=adapter.is_free,
            is_enabled=True,
            is_healthy=True,  # assume healthy until a health check says otherwise
            model_count=model_count,
            adapter_type=type(adapter).__name__,
            last_health_check=None,
        )

    def get_provider(self, name: str) -> ProviderAdapter:
        """Return the adapter for *name*, raising KeyError if not registered."""
        try:
            return self._adapters[name]
        except KeyError:
            raise KeyError(f"Provider '{name}' is not registered. Available: {list(self._adapters)}")

    def list_providers(self) -> list[ProviderInfo]:
        """Return ProviderInfo for every registered provider."""
        return list(self._infos.values())

    async def check_health_all(self) -> dict[str, HealthStatus]:
        """Run health checks on all registered providers and cache results."""
        import asyncio

        async def _check(name: str, adapter: ProviderAdapter) -> tuple[str, HealthStatus]:
            try:
                status = await adapter.check_health()
            except Exception as exc:
                status = HealthStatus(
                    is_healthy=False,
                    latency_ms=0,
                    error=str(exc),
                    last_checked=datetime.utcnow(),
                )
            return name, status

        results = await asyncio.gather(
            *[_check(name, adapter) for name, adapter in self._adapters.items()],
            return_exceptions=False,
        )

        for name, status in results:
            self._health_cache[name] = status
            if name in self._infos:
                info = self._infos[name]
                self._infos[name] = ProviderInfo(
                    name=info.name,
                    display_name=info.display_name,
                    is_free=info.is_free,
                    is_enabled=info.is_enabled,
                    is_healthy=status.is_healthy,
                    model_count=info.model_count,
                    adapter_type=info.adapter_type,
                    last_health_check=status.last_checked,
                )
            logger.info(
                "provider_health_checked",
                provider=name,
                healthy=status.is_healthy,
                latency_ms=status.latency_ms,
            )

        return dict(results)

    def get_free_providers(self) -> list[ProviderInfo]:
        """Return only providers marked as free."""
        return [info for info in self._infos.values() if info.is_free]

    def get_enabled_providers(self) -> list[ProviderInfo]:
        """Return only providers that are enabled."""
        return [info for info in self._infos.values() if info.is_enabled]

    def disable_provider(self, name: str) -> None:
        """Mark a provider as disabled so it is excluded from routing."""
        if name in self._infos:
            info = self._infos[name]
            self._infos[name] = ProviderInfo(
                name=info.name,
                display_name=info.display_name,
                is_free=info.is_free,
                is_enabled=False,
                is_healthy=info.is_healthy,
                model_count=info.model_count,
                adapter_type=info.adapter_type,
                last_health_check=info.last_health_check,
            )

    def enable_provider(self, name: str) -> None:
        """Re-enable a previously disabled provider."""
        if name in self._infos:
            info = self._infos[name]
            self._infos[name] = ProviderInfo(
                name=info.name,
                display_name=info.display_name,
                is_free=info.is_free,
                is_enabled=True,
                is_healthy=info.is_healthy,
                model_count=info.model_count,
                adapter_type=info.adapter_type,
                last_health_check=info.last_health_check,
            )

    def __contains__(self, name: str) -> bool:
        return name in self._adapters

    def __len__(self) -> int:
        return len(self._adapters)
