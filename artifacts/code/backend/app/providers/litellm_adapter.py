"""LiteLLM-based adapter for OpenAI-compatible providers.

Supports: Groq, NVIDIA NIM, Together AI, Cerebras, Fireworks AI, Mistral, OpenRouter.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, AsyncIterator

import structlog

from app.providers.base import (
    CompletionResponse,
    HealthStatus,
    ModelInfo,
    ProviderConfig,
    RateLimitInfo,
)

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

# Hardcoded model catalogs per provider name
_MODEL_CATALOG: dict[str, list[dict[str, Any]]] = {
    "groq": [
        {
            "name": "llama-3.3-70b-versatile",
            "display_name": "Llama 3.3 70B Versatile",
            "context_window": 128_000,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "llama-3.1-8b-instant",
            "display_name": "Llama 3.1 8B Instant",
            "context_window": 128_000,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "mixtral-8x7b-32768",
            "display_name": "Mixtral 8x7B",
            "context_window": 32_768,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "gemma2-9b-it",
            "display_name": "Gemma 2 9B",
            "context_window": 8_192,
            "supports_tools": False,
            "supports_streaming": True,
        },
        {
            "name": "deepseek-r1-distill-llama-70b",
            "display_name": "DeepSeek R1 Distill Llama 70B",
            "context_window": 128_000,
            "supports_tools": False,
            "supports_streaming": True,
        },
    ],
    "nvidia": [
        {
            "name": "meta/llama-3.3-70b-instruct",
            "display_name": "Llama 3.3 70B Instruct (NVIDIA)",
            "context_window": 128_000,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "meta/llama-3.1-405b-instruct",
            "display_name": "Llama 3.1 405B Instruct (NVIDIA)",
            "context_window": 128_000,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "mistralai/mistral-7b-instruct-v0.3",
            "display_name": "Mistral 7B Instruct (NVIDIA)",
            "context_window": 32_768,
            "supports_tools": False,
            "supports_streaming": True,
        },
        {
            "name": "nvidia/llama-3.1-nemotron-70b-instruct",
            "display_name": "Nemotron 70B Instruct",
            "context_window": 128_000,
            "supports_tools": True,
            "supports_streaming": True,
        },
    ],
    "together": [
        {
            "name": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "display_name": "Llama 3.3 70B Turbo (Together)",
            "context_window": 128_000,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "deepseek-ai/DeepSeek-R1",
            "display_name": "DeepSeek R1 (Together)",
            "context_window": 64_000,
            "supports_tools": False,
            "supports_streaming": True,
        },
        {
            "name": "mistralai/Mixtral-8x22B-Instruct-v0.1",
            "display_name": "Mixtral 8x22B Instruct (Together)",
            "context_window": 65_536,
            "supports_tools": True,
            "supports_streaming": True,
        },
    ],
    "cerebras": [
        {
            "name": "llama3.3-70b",
            "display_name": "Llama 3.3 70B (Cerebras)",
            "context_window": 128_000,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "llama3.1-8b",
            "display_name": "Llama 3.1 8B (Cerebras)",
            "context_window": 128_000,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "deepseek-r1-distill-llama-70b",
            "display_name": "DeepSeek R1 Distill Llama 70B (Cerebras)",
            "context_window": 64_000,
            "supports_tools": False,
            "supports_streaming": True,
        },
    ],
    "fireworks": [
        {
            "name": "accounts/fireworks/models/llama-v3p3-70b-instruct",
            "display_name": "Llama 3.3 70B Instruct (Fireworks)",
            "context_window": 128_000,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "accounts/fireworks/models/deepseek-r1",
            "display_name": "DeepSeek R1 (Fireworks)",
            "context_window": 64_000,
            "supports_tools": False,
            "supports_streaming": True,
        },
        {
            "name": "accounts/fireworks/models/mixtral-8x22b-instruct",
            "display_name": "Mixtral 8x22B (Fireworks)",
            "context_window": 65_536,
            "supports_tools": True,
            "supports_streaming": True,
        },
    ],
    "mistral": [
        {
            "name": "mistral-large-latest",
            "display_name": "Mistral Large",
            "context_window": 131_072,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "mistral-small-latest",
            "display_name": "Mistral Small",
            "context_window": 131_072,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "codestral-latest",
            "display_name": "Codestral",
            "context_window": 256_000,
            "supports_tools": False,
            "supports_streaming": True,
        },
        {
            "name": "open-mistral-nemo",
            "display_name": "Mistral Nemo",
            "context_window": 131_072,
            "supports_tools": True,
            "supports_streaming": True,
        },
    ],
    "openrouter": [
        {
            "name": "openrouter/auto",
            "display_name": "OpenRouter Auto",
            "context_window": 200_000,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "google/gemini-2.0-flash-exp:free",
            "display_name": "Gemini 2.0 Flash (free)",
            "context_window": 1_048_576,
            "supports_tools": True,
            "supports_streaming": True,
        },
        {
            "name": "deepseek/deepseek-r1:free",
            "display_name": "DeepSeek R1 (free)",
            "context_window": 64_000,
            "supports_tools": False,
            "supports_streaming": True,
        },
        {
            "name": "meta-llama/llama-3.3-70b-instruct:free",
            "display_name": "Llama 3.3 70B (free)",
            "context_window": 128_000,
            "supports_tools": True,
            "supports_streaming": True,
        },
    ],
}


def _build_litellm_model_name(provider_prefix: str, model: str) -> str:
    """Construct the litellm model string.

    For most providers litellm expects ``<prefix>/<model>``.
    For nvidia_nim the prefix is ``nvidia_nim``.
    """
    return f"{provider_prefix}/{model}"


class LiteLLMAdapter:
    """Provider adapter backed by litellm for OpenAI-compatible endpoints."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self.name: str = config.name
        self.display_name: str = config.display_name
        self.is_free: bool = config.is_free
        self._api_key: str = ""  # set during initialize via registry
        self._api_base: str | None = config.api_base_url
        self._litellm_prefix: str = config.config.get("litellm_prefix", config.name)

    # ── ProviderAdapter Protocol ──────────────────────────────────────────────

    def set_api_key(self, api_key: str) -> None:
        """Inject the API key (called by registry after resolving from settings)."""
        self._api_key = api_key

    async def list_models(self) -> list[ModelInfo]:
        """Return hardcoded model list for this provider."""
        catalog = _MODEL_CATALOG.get(self.name, [])
        return [
            ModelInfo(
                name=entry["name"],
                display_name=entry["display_name"],
                provider=self.name,
                context_window=entry["context_window"],
                supports_tools=entry.get("supports_tools", False),
                supports_streaming=entry.get("supports_streaming", False),
                supports_vision=entry.get("supports_vision", False),
                is_free=self.is_free,
                cost_per_1k_input=entry.get("cost_per_1k_input", 0.0),
                cost_per_1k_output=entry.get("cost_per_1k_output", 0.0),
                capability_tags=entry.get("capability_tags", []),
            )
            for entry in catalog
        ]

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        tools: list[dict] | None = None,
        timeout: float = 120.0,
    ) -> CompletionResponse:
        """Execute a chat completion via litellm."""
        import litellm  # type: ignore[import]

        litellm_model = _build_litellm_model_name(self._litellm_prefix, model)

        call_kwargs: dict[str, Any] = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temperature,
            "timeout": timeout,
            "api_key": self._api_key,
        }
        if self._api_base:
            call_kwargs["api_base"] = self._api_base
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        if tools:
            call_kwargs["tools"] = tools

        start_ms = int(time.monotonic() * 1000)
        try:
            response = await litellm.acompletion(**call_kwargs)
        except Exception as exc:
            logger.error(
                "litellm_completion_failed",
                provider=self.name,
                model=model,
                error=str(exc),
            )
            raise

        latency_ms = int(time.monotonic() * 1000) - start_ms

        choice = response.choices[0]
        message = choice.message
        usage = response.usage or {}

        tokens_input = getattr(usage, "prompt_tokens", 0) or 0
        tokens_output = getattr(usage, "completion_tokens", 0) or 0

        # litellm may compute cost automatically
        cost: float = 0.0
        try:
            cost = float(litellm.completion_cost(completion_response=response))
        except Exception:
            cost = 0.0

        tool_calls_raw: list[dict] | None = None
        if message.tool_calls:
            tool_calls_raw = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]

        return CompletionResponse(
            content=message.content or "",
            model=model,
            provider=self.name,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost=cost,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason or "stop",
            tool_calls=tool_calls_raw,
            raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    async def stream_completion(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 120.0,
    ) -> AsyncIterator[str]:
        """Stream tokens from litellm."""
        import litellm  # type: ignore[import]

        litellm_model = _build_litellm_model_name(self._litellm_prefix, model)

        call_kwargs: dict[str, Any] = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temperature,
            "timeout": timeout,
            "api_key": self._api_key,
            "stream": True,
        }
        if self._api_base:
            call_kwargs["api_base"] = self._api_base
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens

        response = await litellm.acompletion(**call_kwargs)
        return _stream_litellm_response(response)

    async def check_health(self) -> HealthStatus:
        """Perform a minimal completion to verify the provider is reachable."""
        import litellm  # type: ignore[import]

        # Pick the first model from catalog, fall back to a generic name
        catalog = _MODEL_CATALOG.get(self.name, [])
        probe_model = catalog[0]["name"] if catalog else "gpt-3.5-turbo"
        litellm_model = _build_litellm_model_name(self._litellm_prefix, probe_model)

        start_ms = int(time.monotonic() * 1000)
        try:
            await litellm.acompletion(
                model=litellm_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                api_key=self._api_key,
                api_base=self._api_base or litellm.utils.get_api_base(litellm_model, {}),
                timeout=10.0,
            )
            latency_ms = int(time.monotonic() * 1000) - start_ms
            return HealthStatus(
                is_healthy=True,
                latency_ms=latency_ms,
                last_checked=datetime.utcnow(),
            )
        except Exception as exc:
            latency_ms = int(time.monotonic() * 1000) - start_ms
            return HealthStatus(
                is_healthy=False,
                latency_ms=latency_ms,
                error=str(exc),
                last_checked=datetime.utcnow(),
            )

    async def get_rate_limits(self) -> RateLimitInfo:
        """Return static rate limit info (provider-specific limits are not surfaced by litellm)."""
        _LIMITS: dict[str, dict[str, int]] = {
            "groq": {"rpm": 30, "rpd": 14_400, "tpm": 6_000},
            "cerebras": {"rpm": 30, "rpd": 0, "tpm": 60_000},
            "nvidia": {"rpm": 40, "rpd": 0, "tpm": 40_000},
            "together": {"rpm": 60, "rpd": 0, "tpm": 0},
            "fireworks": {"rpm": 60, "rpd": 0, "tpm": 0},
            "mistral": {"rpm": 60, "rpd": 0, "tpm": 0},
            "openrouter": {"rpm": 20, "rpd": 200, "tpm": 0},
        }
        limits = _LIMITS.get(self.name, {"rpm": 60, "rpd": 0, "tpm": 0})
        return RateLimitInfo(
            rpm_limit=limits["rpm"],
            rpd_limit=limits["rpd"],
            rpm_remaining=limits["rpm"],
            rpd_remaining=limits["rpd"],
            tpm_limit=limits["tpm"],
        )


async def _stream_litellm_response(response: Any) -> AsyncIterator[str]:
    """Async generator that yields text chunks from a litellm streaming response."""
    async for chunk in response:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content
