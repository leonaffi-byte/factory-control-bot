"""Base provider DTOs and Protocol definitions."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Protocol


@dataclass
class CompletionResponse:
    content: str
    model: str
    provider: str
    tokens_input: int
    tokens_output: int
    cost: float  # 0.0 for free
    latency_ms: int
    finish_reason: str  # "stop" | "length" | "tool_calls"
    tool_calls: list[dict] | None = None
    raw_response: dict | None = None


@dataclass
class ModelInfo:
    name: str
    display_name: str
    provider: str
    context_window: int
    supports_tools: bool = False
    supports_streaming: bool = False
    supports_vision: bool = False
    is_free: bool = True
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    capability_tags: list[str] = field(default_factory=list)


@dataclass
class HealthStatus:
    is_healthy: bool
    latency_ms: int
    error: str | None = None
    last_checked: datetime | None = None


@dataclass
class RateLimitInfo:
    rpm_limit: int
    rpd_limit: int
    rpm_remaining: int
    rpd_remaining: int
    tpm_limit: int = 0
    reset_at: datetime | None = None


@dataclass
class ProviderConfig:
    name: str
    display_name: str
    api_base_url: str | None
    api_key_env_var: str
    is_free: bool
    priority_score: int
    openai_compatible: bool
    adapter_type: str  # "litellm" | "google_ai" | "sambanova" | "clink"
    config: dict = field(default_factory=dict)


@dataclass
class ProviderInfo:
    name: str
    display_name: str
    is_free: bool
    is_enabled: bool
    is_healthy: bool
    model_count: int
    adapter_type: str
    last_health_check: datetime | None = None


@dataclass
class ModelRecommendation:
    role: str
    provider: str
    model: str
    score: float
    reason: str
    context_window: int
    capability_tags: list[str] = field(default_factory=list)


class ProviderAdapter(Protocol):
    name: str
    display_name: str
    is_free: bool

    async def list_models(self) -> list[ModelInfo]: ...

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
    ) -> CompletionResponse: ...

    async def stream_completion(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 120.0,
    ) -> AsyncIterator[str]: ...

    async def check_health(self) -> HealthStatus: ...

    async def get_rate_limits(self) -> RateLimitInfo: ...
