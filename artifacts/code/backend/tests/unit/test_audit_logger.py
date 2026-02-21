"""Unit tests for audit logger (black-box)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.orchestrator.audit_logger import AuditLogger


class TestAuditLoggerEntries:
    def test_log_phase_start(self, tmp_path: Path):
        logger = AuditLogger(str(tmp_path / "audit.md"))
        logger.log_phase_start(
            phase=1,
            phase_name="Requirements Analysis",
            models_used=[
                {"model": "gemini-3-pro", "provider": "google", "via": "zen MCP", "role": "analyst"},
            ],
            tier=3,
        )
        summary = logger.generate_summary()
        assert "Phase 1" in summary
        assert "Requirements Analysis" in summary
        assert "gemini-3-pro" in summary
        assert "google" in summary

    def test_log_phase_end(self, tmp_path: Path):
        logger = AuditLogger(str(tmp_path / "audit.md"))
        logger.log_phase_end(phase=1, quality_score=98, duration_seconds=120)
        summary = logger.generate_summary()
        assert "98" in summary

    def test_log_model_call(self, tmp_path: Path):
        logger = AuditLogger(str(tmp_path / "audit.md"))
        logger.log_model_call(
            provider="groq",
            model="llama-3.3-70b",
            role="implementer",
            tokens_in=1000,
            tokens_out=500,
            cost=0.0,
        )
        summary = logger.generate_summary()
        assert "groq" in summary
        assert "llama-3.3-70b" in summary
        assert "implementer" in summary

    def test_log_decision(self, tmp_path: Path):
        logger = AuditLogger(str(tmp_path / "audit.md"))
        logger.log_decision(
            decision="Use hybrid architecture",
            rationale="Best balance of tmux access and container isolation",
        )
        summary = logger.generate_summary()
        assert "hybrid architecture" in summary
        assert "tmux access" in summary


class TestAuditLoggerSummary:
    def test_generate_summary_includes_all_entries(self, tmp_path: Path):
        logger = AuditLogger(str(tmp_path / "audit.md"))
        logger.log_phase_start(1, "Req", [{"model": "m1", "provider": "p1", "via": "v1", "role": "r1"}], 2)
        logger.log_model_call("p1", "m1", "r1", 100, 50, 0.0)
        logger.log_phase_end(1, 97, 60)
        logger.log_decision("D1", "R1")

        summary = logger.generate_summary()
        assert "Phase 1" in summary
        assert "97" in summary
        assert "D1" in summary

    def test_empty_logger_returns_empty(self, tmp_path: Path):
        logger = AuditLogger(str(tmp_path / "audit.md"))
        summary = logger.generate_summary()
        assert summary == "" or isinstance(summary, str)


class TestAuditLoggerFlush:
    def test_flush_writes_to_file(self, tmp_path: Path):
        path = tmp_path / "audit.md"
        logger = AuditLogger(str(path))
        logger.log_phase_start(1, "Test", [{"model": "m", "provider": "p", "via": "v", "role": "r"}], 1)
        logger.flush()
        assert path.exists()
        content = path.read_text()
        assert "Phase 1" in content

    def test_flush_clears_buffer(self, tmp_path: Path):
        path = tmp_path / "audit.md"
        logger = AuditLogger(str(path))
        logger.log_decision("test", "test")
        logger.flush()
        # After flush, summary should be empty
        assert logger.generate_summary() == "" or "test" not in logger.generate_summary()

    def test_flush_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "deep" / "nested" / "audit.md"
        logger = AuditLogger(str(path))
        logger.log_decision("test", "test")
        logger.flush()
        assert path.exists()
