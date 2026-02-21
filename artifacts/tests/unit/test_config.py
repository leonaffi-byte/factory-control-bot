"""Unit tests for Settings configuration (black-box, per spec-v2.md)."""

from __future__ import annotations

import pytest


class TestSettingsDefaults:
    def test_database_url_default(self, mock_settings):
        assert "postgresql" in mock_settings.database_url

    def test_default_routing_mode(self, mock_settings):
        assert mock_settings.default_routing_mode in ("api_direct", "openrouter", "clink")

    def test_quality_gate_threshold(self, mock_settings):
        assert mock_settings.quality_gate_threshold == 97

    def test_health_check_interval(self, mock_settings):
        assert mock_settings.health_check_interval == 300

    def test_disk_warning_percent(self, mock_settings):
        assert mock_settings.disk_warning_percent == 80

    def test_disk_critical_percent(self, mock_settings):
        assert mock_settings.disk_critical_percent == 90


class TestSettingsAPIKeys:
    """Verify all v2.0 API key fields exist on Settings."""

    @pytest.mark.parametrize(
        "key_name",
        [
            "groq_api_key",
            "openai_api_key",
            "google_api_key",
            "nvidia_api_key",
            "together_api_key",
            "cerebras_api_key",
            "sambanova_api_key",
            "fireworks_api_key",
            "mistral_api_key",
            "openrouter_api_key",
            "perplexity_api_key",
            "github_token",
        ],
    )
    def test_api_key_field_exists(self, mock_settings, key_name: str):
        assert hasattr(mock_settings, key_name)


class TestSettingsValidation:
    def test_database_url_must_start_with_postgresql(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
        monkeypatch.setenv("ADMIN_TELEGRAM_ID", "123")
        monkeypatch.setenv("DATABASE_URL", "mysql://localhost/test")
        from app.config import Settings
        with pytest.raises(Exception):
            Settings()

    def test_log_level_validation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test")
        monkeypatch.setenv("ADMIN_TELEGRAM_ID", "123")
        monkeypatch.setenv("LOG_LEVEL", "INVALID")
        from app.config import Settings
        with pytest.raises(Exception):
            Settings()


class TestSettingsMasking:
    def test_mask_key_short(self, mock_settings):
        assert mock_settings.mask_key("abc") == "****"

    def test_mask_key_long(self, mock_settings):
        masked = mock_settings.mask_key("sk-1234567890abcdef")
        assert masked.startswith("sk-1")
        assert masked.endswith("cdef")
        assert "..." in masked

    def test_get_masked_keys_includes_new_providers(self, mock_settings):
        masked = mock_settings.get_masked_keys()
        assert "nvidia_api_key" in masked
        assert "together_api_key" in masked
        assert "cerebras_api_key" in masked
        assert "sambanova_api_key" in masked
        assert "fireworks_api_key" in masked
        assert "mistral_api_key" in masked


class TestSettingsBackup:
    def test_backup_dir_field_exists(self, mock_settings):
        assert hasattr(mock_settings, "backup_dir")
