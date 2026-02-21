"""Google AI Studio adapter using the google.generativeai SDK."""
from __future__ import annotations

import time
from datetime import datetime
from typing import AsyncIterator

import structlog

from app.providers.base import (
    CompletionResponse,
    HealthStatus,
    ModelInfo,
    RateLimitInfo,
)

logger = structlog.get_logger()

# Supported models and their properties
_GOOGLE_MODELS: list[dict] = [
    {
        "name": "gemini-2.0-flash",
        "display_name": "Gemini 2.0 Flash",
        "context_window": 1_048_576,
        "supports_tools": True,
        "supports_streaming": True,
        "supports_vision": True,
    },
    {
        "name": "gemini-1.5-flash",
        "display_name": "Gemini 1.5 Flash",
        "context_window": 1_048_576,
        "supports_tools": True,
        "supports_streaming": True,
        "supports_vision": True,
    },
    {
        "name": "gemini-1.5-pro",
        "display_name": "Gemini 1.5 Pro",
        "context_window": 2_097_152,
        "supports_tools": True,
        "supports_streaming": True,
        "supports_vision": True,
    },
]

# Map OpenAI role names -> Google role names
_ROLE_MAP: dict[str, str] = {
    "user": "user",
    "assistant": "model",
    "system": "user",  # Google AI Studio handles system prompts differently
}


def _messages_to_google_parts(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Convert OpenAI-style messages to Google GenerativeAI format.

    Returns (system_instruction, contents_list).
    """
    system_instruction: str | None = None
    contents: list[dict] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            # Google AI Studio accepts system_instruction separately
            system_instruction = content
            continue

        google_role = _ROLE_MAP.get(role, "user")
        contents.append({"role": google_role, "parts": [{"text": content}]})

    return system_instruction, contents


class GoogleAIAdapter:
    """Adapter for Google AI Studio (Gemini models) via google.generativeai."""

    name: str = "google_ai"
    display_name: str = "Google AI Studio"
    is_free: bool = True

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._configure()

    def _configure(self) -> None:
        try:
            import google.generativeai as genai  # type: ignore[import]

            genai.configure(api_key=self._api_key)
        except ImportError:
            logger.warning("google_generativeai_not_installed")

    # ── ProviderAdapter Protocol ──────────────────────────────────────────────

    async def list_models(self) -> list[ModelInfo]:
        """Return the hardcoded Gemini model list."""
        return [
            ModelInfo(
                name=m["name"],
                display_name=m["display_name"],
                provider=self.name,
                context_window=m["context_window"],
                supports_tools=m.get("supports_tools", False),
                supports_streaming=m.get("supports_streaming", False),
                supports_vision=m.get("supports_vision", False),
                is_free=True,
                cost_per_1k_input=0.0,
                cost_per_1k_output=0.0,
                capability_tags=["vision", "long-context", "multimodal"],
            )
            for m in _GOOGLE_MODELS
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
        """Execute a chat completion via Google AI Studio."""
        import google.generativeai as genai  # type: ignore[import]

        system_instruction, contents = _messages_to_google_parts(messages)

        gen_config: dict = {"temperature": temperature}
        if max_tokens is not None:
            gen_config["max_output_tokens"] = max_tokens

        model_obj = genai.GenerativeModel(
            model_name=model,
            generation_config=genai.GenerationConfig(**gen_config),
            system_instruction=system_instruction,
        )

        start_ms = int(time.monotonic() * 1000)
        try:
            response = await model_obj.generate_content_async(
                contents,
                request_options={"timeout": timeout},
            )
        except Exception as exc:
            logger.error(
                "google_ai_completion_failed",
                model=model,
                error=str(exc),
            )
            raise

        latency_ms = int(time.monotonic() * 1000) - start_ms

        # Extract text content
        text_content = ""
        try:
            text_content = response.text
        except Exception:
            # Aggregate parts manually if .text raises
            for candidate in response.candidates:
                for part in candidate.content.parts:
                    if hasattr(part, "text"):
                        text_content += part.text

        # Extract token usage from response metadata
        tokens_input = 0
        tokens_output = 0
        try:
            usage = response.usage_metadata
            tokens_input = usage.prompt_token_count or 0
            tokens_output = usage.candidates_token_count or 0
        except Exception:
            pass

        finish_reason = "stop"
        try:
            candidate = response.candidates[0]
            finish_reason = str(candidate.finish_reason).lower().replace("finish_reason.", "")
        except Exception:
            pass

        return CompletionResponse(
            content=text_content,
            model=model,
            provider=self.name,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost=0.0,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            tool_calls=None,
            raw_response=None,
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
        """Stream tokens from Google AI Studio."""
        import google.generativeai as genai  # type: ignore[import]

        system_instruction, contents = _messages_to_google_parts(messages)

        gen_config: dict = {"temperature": temperature}
        if max_tokens is not None:
            gen_config["max_output_tokens"] = max_tokens

        model_obj = genai.GenerativeModel(
            model_name=model,
            generation_config=genai.GenerationConfig(**gen_config),
            system_instruction=system_instruction,
        )

        response = await model_obj.generate_content_async(
            contents,
            stream=True,
            request_options={"timeout": timeout},
        )
        return _stream_google_response(response)

    async def check_health(self) -> HealthStatus:
        """Verify Google AI Studio is reachable with a minimal call."""
        import google.generativeai as genai  # type: ignore[import]

        probe_model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        start_ms = int(time.monotonic() * 1000)
        try:
            await probe_model.generate_content_async(
                "ping",
                generation_config=genai.GenerationConfig(max_output_tokens=1),
                request_options={"timeout": 10.0},
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
        """Return Google AI Studio free-tier rate limits."""
        return RateLimitInfo(
            rpm_limit=15,
            rpd_limit=1_500,
            rpm_remaining=15,
            rpd_remaining=1_500,
            tpm_limit=1_000_000,
        )


async def _stream_google_response(response) -> AsyncIterator[str]:  # type: ignore[no-untyped-def]
    """Async generator yielding text chunks from a streaming Google AI response."""
    async for chunk in response:
        try:
            if chunk.text:
                yield chunk.text
        except Exception:
            pass
