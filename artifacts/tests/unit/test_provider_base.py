"""Unit tests for provider base DTOs (black-box, per interfaces-v2.md)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.providers.base import (
    CompletionResponse,
    HealthStatus,
    ModelInfo,
    ModelRecommendation,
    ProviderConfig,
    ProviderInfo,
    RateLimitInfo,
)


class TestCompletionResponse:
    def test_create_with_all_fields(self):
        resp = CompletionResponse(
            content="hello world",
            model="gpt-test",
            provider="test-provider",
            tokens_input=12,
            tokens_output=34,
            cost=0.001,
            latency_ms=123,
            finish_reason="stop",
            tool_calls=[{"name": "tool", "args": {"x": 1}}],
            raw_response={"id": "abc"},
        )
        assert resp.content == "hello world"
        assert resp.model == "gpt-test"
        assert resp.provider == "test-provider"
        assert resp.tokens_input == 12
        assert resp.tokens_output == 34
        assert resp.cost == pytest.approx(0.001)
        assert resp.latency_ms == 123
        assert resp.finish_reason == "stop"
        assert resp.tool_calls == [{"name": "tool", "args": {"x": 1}}]
        assert resp.raw_response == {"id": "abc"}

    def test_create_with_defaults(self):
        resp = CompletionResponse(
            content="test",
            model="m",
            provider="p",
            tokens_input=0,
            tokens_output=0,
            cost=0.0,
            latency_ms=0,
            finish_reason="stop",
        )
        assert resp.tool_calls is None
        assert resp.raw_response is None

    def test_free_cost_is_zero(self):
        resp = CompletionResponse(
            content="free",
            model="free-model",
            provider="free-provider",
            tokens_input=100,
            tokens_output=50,
            cost=0.0,
            latency_ms=200,
            finish_reason="stop",
        )
        assert resp.cost == 0.0


class TestModelInfo:
    def test_capability_tags(self):
        mi = ModelInfo(
            name="model-a",
            display_name="Model A",
            provider="test-provider",
            context_window=128000,
            supports_tools=True,
            supports_streaming=True,
            supports_vision=False,
            is_free=True,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
            capability_tags=["reasoning", "code"],
        )
        assert mi.capability_tags == ["reasoning", "code"]
        assert mi.supports_tools is True
        assert mi.context_window == 128000
        assert mi.is_free is True

    def test_defaults(self):
        mi = ModelInfo(
            name="m",
            display_name="M",
            provider="p",
            context_window=4096,
        )
        assert mi.supports_tools is False
        assert mi.supports_streaming is False
        assert mi.supports_vision is False
        assert mi.is_free is True
        assert mi.cost_per_1k_input == 0.0
        assert mi.cost_per_1k_output == 0.0
        assert mi.capability_tags == []


class TestHealthStatus:
    def test_healthy_state(self):
        hs = HealthStatus(
            is_healthy=True,
            latency_ms=42,
            error=None,
            last_checked=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert hs.is_healthy is True
        assert hs.error is None
        assert hs.latency_ms == 42

    def test_unhealthy_state(self):
        hs = HealthStatus(
            is_healthy=False,
            latency_ms=999,
            error="timeout",
            last_checked=None,
        )
        assert hs.is_healthy is False
        assert hs.error == "timeout"
        assert hs.last_checked is None


class TestRateLimitInfo:
    def test_remaining_limits(self):
        rl = RateLimitInfo(
            rpm_limit=60,
            rpd_limit=1000,
            rpm_remaining=12,
            rpd_remaining=345,
            tpm_limit=120000,
            reset_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert rl.rpm_limit == 60
        assert rl.rpm_remaining == 12
        assert rl.rpd_limit == 1000
        assert rl.rpd_remaining == 345
        assert rl.tpm_limit == 120000
        assert isinstance(rl.reset_at, datetime)

    def test_defaults(self):
        rl = RateLimitInfo(
            rpm_limit=30,
            rpd_limit=500,
            rpm_remaining=30,
            rpd_remaining=500,
        )
        assert rl.tpm_limit == 0
        assert rl.reset_at is None


class TestProviderConfig:
    @pytest.mark.parametrize(
        "adapter_type,openai_compatible",
        [
            ("litellm", True),
            ("google_ai", False),
            ("sambanova", False),
            ("clink", False),
        ],
    )
    def test_different_adapter_types(self, adapter_type: str, openai_compatible: bool):
        pc = ProviderConfig(
            name=f"{adapter_type}-provider",
            display_name=f"{adapter_type.title()} Provider",
            api_base_url="https://api.example.com",
            api_key_env_var="TEST_API_KEY",
            is_free=True,
            priority_score=10,
            openai_compatible=openai_compatible,
            adapter_type=adapter_type,
            config={"timeout": 30},
        )
        assert pc.adapter_type == adapter_type
        assert pc.openai_compatible is openai_compatible
        assert pc.config == {"timeout": 30}

    def test_default_config(self):
        pc = ProviderConfig(
            name="test",
            display_name="Test",
            api_base_url=None,
            api_key_env_var="KEY",
            is_free=True,
            priority_score=0,
            openai_compatible=True,
            adapter_type="litellm",
        )
        assert pc.config == {}
        assert pc.api_base_url is None


class TestProviderInfo:
    def test_provider_info_fields(self):
        pi = ProviderInfo(
            name="groq",
            display_name="Groq",
            is_free=True,
            is_enabled=True,
            is_healthy=True,
            model_count=5,
            adapter_type="litellm",
            last_health_check=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert pi.name == "groq"
        assert pi.is_free is True
        assert pi.is_enabled is True
        assert pi.model_count == 5


class TestModelRecommendation:
    def test_recommendation_fields(self):
        rec = ModelRecommendation(
            role="implementer",
            provider="groq",
            model="llama-3.3-70b",
            score=85.0,
            reason="Best HumanEval score among free models",
            context_window=128000,
            capability_tags=["code", "reasoning"],
        )
        assert rec.role == "implementer"
        assert rec.score == pytest.approx(85.0)
        assert rec.reason == "Best HumanEval score among free models"
        assert "code" in rec.capability_tags
