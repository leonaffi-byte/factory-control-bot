"""Unit tests for CLI command parsing (black-box, per spec-v2.md)."""

from __future__ import annotations

import pytest


class TestCLICommandDefinitions:
    """Verify CLI commands exist and accept expected arguments."""

    def test_cli_app_importable(self):
        """The Typer CLI app should be importable."""
        from app.cli.main import app
        assert app is not None

    def test_run_command_exists(self):
        """factory run <project> should be a valid command."""
        from typer.testing import CliRunner
        from app.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "project" in result.output.lower() or "run" in result.output.lower()

    def test_status_command_exists(self):
        from typer.testing import CliRunner
        from app.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0

    def test_stop_command_exists(self):
        from typer.testing import CliRunner
        from app.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["stop", "--help"])
        assert result.exit_code == 0

    def test_scan_models_command_exists(self):
        from typer.testing import CliRunner
        from app.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["scan-models", "--help"])
        assert result.exit_code == 0

    def test_health_command_exists(self):
        from typer.testing import CliRunner
        from app.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["health", "--help"])
        assert result.exit_code == 0

    def test_backup_command_exists(self):
        from typer.testing import CliRunner
        from app.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["backup", "--help"])
        assert result.exit_code == 0

    def test_self_research_command_exists(self):
        from typer.testing import CliRunner
        from app.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["self-research", "--help"])
        assert result.exit_code == 0
