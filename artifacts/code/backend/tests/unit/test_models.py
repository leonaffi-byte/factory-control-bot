"""Unit tests for SQLAlchemy model definitions (black-box, per spec-v2.md)."""

from __future__ import annotations

import pytest


class TestOrchestrationStateModel:
    def test_has_required_fields(self):
        from app.models.orchestration_state import OrchestrationState
        obj = OrchestrationState()
        for field in ("current_phase", "phase_status", "retry_count", "tier", "interface_source"):
            assert hasattr(obj, field)

    def test_default_values(self):
        from app.models.orchestration_state import OrchestrationState
        obj = OrchestrationState()
        assert obj.current_phase == 0
        assert obj.phase_status == "pending"
        assert obj.retry_count == 0
        assert obj.tier == 0
        assert obj.interface_source == "telegram"


class TestModelProviderModel:
    def test_has_required_fields(self):
        from app.models.model_provider import ModelProvider
        obj = ModelProvider()
        for field in ("name", "display_name", "is_free", "is_enabled", "adapter_type", "is_healthy"):
            assert hasattr(obj, field)

    def test_default_values(self):
        from app.models.model_provider import ModelProvider
        obj = ModelProvider()
        assert obj.is_free is False
        assert obj.is_enabled is False
        assert obj.openai_compatible is True
        assert obj.adapter_type == "litellm"
        assert obj.is_healthy is True


class TestApiUsageLogModel:
    def test_has_required_fields(self):
        from app.models.api_usage import ApiUsageLog
        obj = ApiUsageLog()
        for field in ("provider_name", "model_name", "role", "tokens_input", "tokens_output",
                       "cost_estimated", "is_free", "latency_ms", "success"):
            assert hasattr(obj, field)

    def test_default_values(self):
        from app.models.api_usage import ApiUsageLog
        obj = ApiUsageLog()
        assert obj.tokens_input == 0
        assert obj.tokens_output == 0
        assert obj.is_free is True
        assert obj.success is True


class TestModelBenchmarkModel:
    def test_has_required_fields(self):
        from app.models.model_benchmark import ModelBenchmark
        obj = ModelBenchmark()
        for field in ("model_name", "provider_name", "context_window", "benchmark_quality",
                       "capability_tags", "overall_score"):
            assert hasattr(obj, field)


class TestSelfResearchModels:
    def test_report_has_required_fields(self):
        from app.models.self_research import SelfResearchReport
        obj = SelfResearchReport()
        for field in ("triggered_by", "suggestions_count", "accepted_count", "rejected_count"):
            assert hasattr(obj, field)

    def test_suggestion_has_required_fields(self):
        from app.models.self_research import SelfResearchSuggestion
        obj = SelfResearchSuggestion()
        for field in ("category", "title", "description", "risk_level", "status"):
            assert hasattr(obj, field)

    def test_suggestion_default_status(self):
        from app.models.self_research import SelfResearchSuggestion
        obj = SelfResearchSuggestion()
        assert obj.status == "pending"


class TestScheduledTaskModel:
    def test_has_required_fields(self):
        from app.models.scheduled_task import ScheduledTask
        obj = ScheduledTask()
        for field in ("task_type", "cron_expression", "is_enabled"):
            assert hasattr(obj, field)

    def test_default_enabled(self):
        from app.models.scheduled_task import ScheduledTask
        obj = ScheduledTask()
        assert obj.is_enabled is True


class TestBackupModel:
    def test_has_required_fields(self):
        from app.models.backup import Backup
        obj = Backup()
        for field in ("backup_type", "file_path", "sha256_checksum", "schema_version",
                       "includes_db", "includes_projects", "includes_config", "status"):
            assert hasattr(obj, field)

    def test_default_values(self):
        from app.models.backup import Backup
        obj = Backup()
        assert obj.includes_db is True
        assert obj.includes_projects is True
        assert obj.includes_config is True
        assert obj.status == "completed"


class TestFactoryRunExtensions:
    def test_has_interface_source(self):
        from app.models.factory_run import FactoryRun
        obj = FactoryRun()
        assert hasattr(obj, "interface_source")
        assert obj.interface_source == "telegram"

    def test_has_escalated_status(self):
        from app.models.factory_run import RunStatus
        assert hasattr(RunStatus, "ESCALATED")
        assert RunStatus.ESCALATED.value == "escalated"


class TestFactoryEventExtensions:
    def test_has_processed_field(self):
        from app.models.factory_event import FactoryEvent
        obj = FactoryEvent()
        assert hasattr(obj, "processed")
        assert obj.processed is False
