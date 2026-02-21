"""Transcription service — Groq Whisper primary, OpenAI Whisper fallback."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import httpx
import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from app.config import Settings

logger = structlog.get_logger()


class TranscriptionResult(BaseModel):
    """Result of a voice transcription."""
    text: str
    language: str
    provider: str  # "groq" or "openai"
    duration_ms: int


class TranscriptionError(Exception):
    """Raised when both transcription providers fail."""
    pass


class TranscriptionService:
    """
    Voice transcription with Groq primary, OpenAI fallback.

    Fallback logic:
    - Try Groq first
    - On HTTP 429/500/timeout, switch to OpenAI for this request
    - After 3 consecutive Groq failures, use OpenAI for 5 minutes
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings

        self.groq_client = httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            timeout=30.0,
        )
        self.openai_client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=30.0,
        )

        self.groq_failures = 0
        self.groq_cooldown_until: datetime | None = None

    async def close(self) -> None:
        """Close HTTP clients."""
        await self.groq_client.aclose()
        await self.openai_client.aclose()

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
    ) -> TranscriptionResult:
        """
        Transcribe audio bytes using Groq (primary) or OpenAI (fallback).

        Args:
            audio_bytes: Raw audio file bytes
            filename: Original filename (e.g., "voice_123.ogg")

        Returns:
            TranscriptionResult with text, detected language, provider, and duration.

        Raises:
            TranscriptionError: If both providers fail.
        """
        settings = getattr(self, '_settings', None)
        voice_provider = settings.voice_provider if settings else "auto"

        if voice_provider == "openai":
            return await self._transcribe_openai(audio_bytes, filename)
        elif voice_provider == "groq":
            return await self._transcribe_groq(audio_bytes, filename)

        # "auto" mode — try Groq first, fallback to OpenAI
        if self._should_use_groq():
            try:
                result = await self._transcribe_groq(audio_bytes, filename)
                self.groq_failures = 0
                return result
            except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
                logger.warning("groq_transcription_failed", error=str(e))
                self.groq_failures += 1
                if self.groq_failures >= 3:
                    self.groq_cooldown_until = datetime.utcnow() + timedelta(minutes=5)
                    logger.warning("groq_cooldown_activated", until=str(self.groq_cooldown_until))

        # Fallback to OpenAI
        try:
            return await self._transcribe_openai(audio_bytes, filename)
        except Exception as e:
            raise TranscriptionError(f"Both transcription providers failed: {e}") from e

    def _should_use_groq(self) -> bool:
        """Check if Groq should be used (not in cooldown)."""
        settings = getattr(self, '_settings', None)
        if settings and not settings.groq_api_key:
            return False
        if self.groq_cooldown_until and datetime.utcnow() < self.groq_cooldown_until:
            return False
        return True

    async def _transcribe_groq(
        self, audio_bytes: bytes, filename: str
    ) -> TranscriptionResult:
        """Transcribe using Groq Whisper API."""
        start = time.monotonic()

        files = {
            "file": (filename, audio_bytes, "audio/ogg"),
        }
        data = {
            "model": "whisper-large-v3-turbo",
            "response_format": "verbose_json",
        }

        response = await self.groq_client.post(
            "/audio/transcriptions",
            files=files,
            data=data,
        )
        response.raise_for_status()

        result = response.json()
        duration_ms = int((time.monotonic() - start) * 1000)

        return TranscriptionResult(
            text=result.get("text", ""),
            language=result.get("language", "unknown"),
            provider="groq",
            duration_ms=duration_ms,
        )

    async def _transcribe_openai(
        self, audio_bytes: bytes, filename: str
    ) -> TranscriptionResult:
        """Transcribe using OpenAI Whisper API."""
        start = time.monotonic()

        files = {
            "file": (filename, audio_bytes, "audio/ogg"),
        }
        data = {
            "model": "whisper-1",
            "response_format": "verbose_json",
        }

        response = await self.openai_client.post(
            "/audio/transcriptions",
            files=files,
            data=data,
        )
        response.raise_for_status()

        result = response.json()
        duration_ms = int((time.monotonic() - start) * 1000)

        return TranscriptionResult(
            text=result.get("text", ""),
            language=result.get("language", "unknown"),
            provider="openai",
            duration_ms=duration_ms,
        )
