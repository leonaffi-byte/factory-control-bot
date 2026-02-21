"""
Black-box tests for the TranscriptionService.

Tests against spec:
  - Groq Whisper primary, OpenAI Whisper fallback
  - 3 consecutive Groq failures -> 5-minute cooldown
  - Returns TranscriptionResult(text, language, provider, duration_ms)
"""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

import httpx


@pytest.mark.asyncio
class TestTranscriptionService:
    """Test transcription with provider fallback logic."""

    @pytest.fixture
    def mock_groq_success(self):
        """Mock successful Groq transcription."""
        mock = AsyncMock()
        mock.post = AsyncMock(return_value=httpx.Response(
            200,
            json={"text": "hello world", "language": "en"},
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/audio/transcriptions")
        ))
        return mock

    @pytest.fixture
    def mock_groq_failure(self):
        """Mock Groq transcription failure."""
        mock = AsyncMock()
        mock.post = AsyncMock(side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/audio/transcriptions"),
            response=httpx.Response(500)
        ))
        return mock

    @pytest.fixture
    def mock_openai_success(self):
        """Mock successful OpenAI transcription."""
        mock = AsyncMock()
        mock.post = AsyncMock(return_value=httpx.Response(
            200,
            json={"text": "hello world", "language": "en"},
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
        ))
        return mock

    async def test_groq_primary_success(self, mock_groq_success, mock_openai_success):
        """When Groq succeeds, it should be the primary provider used."""
        from app.services.transcription import TranscriptionService
        from app.config import Settings

        with patch.object(Settings, '__init__', lambda self: None):
            service = TranscriptionService.__new__(TranscriptionService)
            service.groq_client = mock_groq_success
            service.openai_client = mock_openai_success
            service.groq_failures = 0
            service.groq_cooldown_until = None

            result = await service.transcribe(b"fake_audio", "test.ogg")

            assert result.text == "hello world"
            assert result.provider == "groq"
            mock_groq_success.post.assert_called_once()
            mock_openai_success.post.assert_not_called()

    async def test_groq_fail_fallback_to_openai(self, mock_groq_failure, mock_openai_success):
        """When Groq fails, should fall back to OpenAI."""
        from app.services.transcription import TranscriptionService

        service = TranscriptionService.__new__(TranscriptionService)
        service.groq_client = mock_groq_failure
        service.openai_client = mock_openai_success
        service.groq_failures = 0
        service.groq_cooldown_until = None

        result = await service.transcribe(b"fake_audio", "test.ogg")

        assert result.text == "hello world"
        assert result.provider == "openai"

    async def test_three_failures_trigger_cooldown(self, mock_groq_failure, mock_openai_success):
        """3 consecutive Groq failures should trigger 5-minute cooldown."""
        from app.services.transcription import TranscriptionService

        service = TranscriptionService.__new__(TranscriptionService)
        service.groq_client = mock_groq_failure
        service.openai_client = mock_openai_success
        service.groq_failures = 2  # Already 2 failures
        service.groq_cooldown_until = None

        # This third failure should trigger cooldown
        result = await service.transcribe(b"fake_audio", "test.ogg")
        assert result.provider == "openai"
        assert service.groq_failures >= 3
        assert service.groq_cooldown_until is not None

    async def test_during_cooldown_uses_openai(self, mock_groq_success, mock_openai_success):
        """During Groq cooldown, should use OpenAI directly."""
        from app.services.transcription import TranscriptionService

        service = TranscriptionService.__new__(TranscriptionService)
        service.groq_client = mock_groq_success
        service.openai_client = mock_openai_success
        service.groq_failures = 3
        service.groq_cooldown_until = datetime.utcnow() + timedelta(minutes=4)

        result = await service.transcribe(b"fake_audio", "test.ogg")
        assert result.provider == "openai"
        mock_groq_success.post.assert_not_called()

    async def test_result_has_required_fields(self, mock_groq_success, mock_openai_success):
        """TranscriptionResult must have text, language, provider, duration_ms."""
        from app.services.transcription import TranscriptionService

        service = TranscriptionService.__new__(TranscriptionService)
        service.groq_client = mock_groq_success
        service.openai_client = mock_openai_success
        service.groq_failures = 0
        service.groq_cooldown_until = None

        result = await service.transcribe(b"fake_audio", "test.ogg")

        assert hasattr(result, "text")
        assert hasattr(result, "language")
        assert hasattr(result, "provider")
        assert hasattr(result, "duration_ms")
        assert isinstance(result.text, str)
        assert isinstance(result.provider, str)
