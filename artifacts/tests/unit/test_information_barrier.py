"""Unit tests for the information barrier (black-box, per interfaces-v2.md)."""

from __future__ import annotations

import pytest

from app.orchestrator.information_barrier import (
    IMPLEMENTER_ALLOWED,
    IMPLEMENTER_BLOCKED,
    TESTER_ALLOWED,
    TESTER_BLOCKED,
    InformationBarrier,
)


class TestBarrierConstants:
    def test_implementer_allowed_non_empty(self):
        assert len(IMPLEMENTER_ALLOWED) > 0

    def test_tester_allowed_non_empty(self):
        assert len(TESTER_ALLOWED) > 0

    def test_implementer_blocked_includes_tests(self):
        assert any("tests" in p for p in IMPLEMENTER_BLOCKED)

    def test_tester_blocked_includes_code(self):
        assert any("code" in p for p in TESTER_BLOCKED)


class TestImplementerAccess:
    @pytest.fixture
    def barrier(self) -> InformationBarrier:
        return InformationBarrier()

    @pytest.mark.parametrize(
        "file_path",
        [
            "artifacts/requirements/spec-v2.md",
            "artifacts/requirements/spec.md",
            "artifacts/architecture/design-v2.md",
            "artifacts/architecture/design.md",
            "artifacts/architecture/interfaces-v2.md",
            "artifacts/architecture/interfaces.md",
        ],
    )
    def test_can_read_allowed_docs(self, barrier: InformationBarrier, file_path: str):
        assert barrier.validate_access("implementer", file_path, "read") is True

    def test_can_write_to_code_dir(self, barrier: InformationBarrier):
        assert barrier.validate_access("implementer", "artifacts/code/backend/main.py", "write") is True

    @pytest.mark.parametrize(
        "file_path",
        [
            "artifacts/tests/test_anything.py",
            "artifacts/tests/unit/test_models.py",
            "artifacts/tests/conftest.py",
        ],
    )
    def test_cannot_read_tests(self, barrier: InformationBarrier, file_path: str):
        assert barrier.validate_access("implementer", file_path, "read") is False


class TestTesterAccess:
    @pytest.fixture
    def barrier(self) -> InformationBarrier:
        return InformationBarrier()

    @pytest.mark.parametrize(
        "file_path",
        [
            "artifacts/requirements/spec-v2.md",
            "artifacts/requirements/spec.md",
            "artifacts/architecture/interfaces-v2.md",
            "artifacts/architecture/interfaces.md",
        ],
    )
    def test_can_read_spec_and_interfaces(self, barrier: InformationBarrier, file_path: str):
        assert barrier.validate_access("tester", file_path, "read") is True

    def test_can_write_to_tests_dir(self, barrier: InformationBarrier):
        assert barrier.validate_access("tester", "artifacts/tests/test_new.py", "write") is True

    @pytest.mark.parametrize(
        "file_path",
        [
            "artifacts/code/backend/main.py",
            "artifacts/code/backend/app/services/factory_runner.py",
            "artifacts/code/frontend/index.html",
        ],
    )
    def test_cannot_read_code(self, barrier: InformationBarrier, file_path: str):
        assert barrier.validate_access("tester", file_path, "read") is False

    def test_cannot_read_design(self, barrier: InformationBarrier):
        assert barrier.validate_access("tester", "artifacts/architecture/design-v2.md", "read") is False


class TestFilterArtifacts:
    @pytest.fixture
    def barrier(self) -> InformationBarrier:
        return InformationBarrier()

    @pytest.fixture
    def all_artifacts(self) -> dict[str, str]:
        return {
            "artifacts/requirements/spec-v2.md": "spec content",
            "artifacts/architecture/interfaces-v2.md": "interfaces content",
            "artifacts/architecture/design-v2.md": "design content",
            "artifacts/tests/test_anything.py": "test content",
            "artifacts/code/backend/main.py": "code content",
        }

    def test_implementer_filter(self, barrier: InformationBarrier, all_artifacts: dict):
        filtered = barrier.filter_artifacts("implementer", all_artifacts)
        assert "artifacts/tests/test_anything.py" not in filtered
        assert "artifacts/requirements/spec-v2.md" in filtered
        assert "artifacts/architecture/interfaces-v2.md" in filtered
        assert "artifacts/architecture/design-v2.md" in filtered

    def test_tester_filter(self, barrier: InformationBarrier, all_artifacts: dict):
        filtered = barrier.filter_artifacts("tester", all_artifacts)
        assert "artifacts/code/backend/main.py" not in filtered
        assert "artifacts/architecture/design-v2.md" not in filtered
        assert "artifacts/requirements/spec-v2.md" in filtered
        assert "artifacts/architecture/interfaces-v2.md" in filtered
