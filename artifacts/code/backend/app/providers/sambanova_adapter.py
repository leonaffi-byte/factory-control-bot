"""SambaNova Cloud adapter using the OpenAI-compatible /chat/completions endpoint."""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import AsyncIterator

import httpx
import structlog

from app.providers.base import (
    CompletionResponse,
    HealthStatus,
    ModelInfo,
    RateLimitInfo,
)

logger = structlog.get_logger()

_SAMBANOVA_API_BASE = "https://api.sambanova.ai/v1"

_SAMBANOVA_MODELS: list[dict] = [
    {
        "name": "Meta-Llama-3.3-70B-Instruct",
        "display_name": "Llama 3.3 70B Instruct (SambaNova)",
        "context_window": 131_072,
        "supports_tools": True,
        "supports_streaming": True,
    },
    {
        "name": "DeepSeek-R1-Distill-Llama-70B",
        "display_name": "DeepSeek R1 Distill Llama 70B (SambaNova)",
        "context_window": 32_768,
        "supports_tools": False,
        "supports_streaming": True,
    },
    {
        "name": "Qwen2.5-72B-Instruct",
        "display_name": "Qwen 2.5 72B Instruct (SambaNova)",
        "context_window": 32_768,
        "supports_tools": True,
        "supports_streaming": True,
    },
]


class SambaNovAdapter:
    """Provider adapter for SambaNova Cloud via direct HTTP (OpenAI-compatible API)."""

    name: str = "sambanova"
    display_name: str = "SambaNova Cloud"
    is_free: bool = True

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._base_url = _SAMBANOVA_API_BASE
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _make_client(self, timeout: float = 120.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=httpx.Timeout(timeout),
        )

    # ── ProviderAdapter Protocol ──────────────────────────────────────────────

    async def list_models(self) -> list[ModelInfo]:
        """Return hardcoded SambaNova model list."""
        return [
            ModelInfo(
                name=m["name"],
                display_name=m["display_name"],
                provider=self.name,
                context_window=m["context_window"],
                supports_tools=m.get("supports_tools", False),
                supports_streaming=m.get("supports_streaming", False),
                supports_vision=False,
                is_free=True,
                cost_per_1k_input=0.0,
                cost_per_1k_output=0.0,
                capability_tags=["fast-inference"],
            )
            for m in _SAMBANOVA_MODELS
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
        """Execute a chat completion against the SambaNova API."""
        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools

        start_ms = int(time.monotonic() * 1000)
        try:
            async with self._make_client(timeout) as client:
                resp = await client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "sambanova_http_error",
                model=model,
                status=exc.response.status_code,
                body=exc.response.text[:300],
            )
            raise
        except Exception as exc:
            logger.error("sambanova_request_failed", model=model, error=str(exc))
            raise

        latency_ms = int(time.monotonic() * 1000) - start_ms

        choice = data["choices"][0]
        message = choice["message"]
        usage = data.get("usage", {})

        tool_calls_raw: list[dict] | None = None
        if message.get("tool_calls"):
            tool_calls_raw = message["tool_calls"]

        return CompletionResponse(
            content=message.get("content") or "",
            model=model,
            provider=self.name,
            tokens_input=usage.get("prompt_tokens", 0),
            tokens_output=usage.get("completion_tokens", 0),
            cost=0.0,
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason", "stop"),
            tool_calls=tool_calls_raw,
            raw_response=data,
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
        """Stream tokens from SambaNova using SSE."""
        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        return _stream_sambanova(self._make_client(timeout), payload)

    async def check_health(self) -> HealthStatus:
        """Probe SambaNova with a minimal request."""
        probe_payload = {
            "model": _SAMBANOVA_MODELS[0]["name"],
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "stream": False,
        }
        start_ms = int(time.monotonic() * 1000)
        try:
            async with self._make_client(timeout=10.0) as client:
                resp = await client.post("/chat/completions", json=probe_payload)
                resp.raise_for_status()
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
        """Return SambaNova free-tier rate limits."""
        return RateLimitInfo(
            rpm_limit=60,
            rpd_limit=0,
            rpm_remaining=60,
            rpd_remaining=0,
            tpm_limit=0,
        )


async def _stream_sambanova(
    client_factory: httpx.AsyncClient,
    payload: dict,
) -> AsyncIterator[str]:
    """Async generator that yields text chunks from SambaNova's SSE stream."""
    async with client_factory as client:
        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[len("data:"):].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
