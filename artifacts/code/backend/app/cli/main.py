"""Factory Control Bot — main CLI application entry point."""

from __future__ import annotations

import typer
from rich.console import Console

# Import all command group sub-apps
from app.cli.commands.run import app as run_app
from app.cli.commands.status import app as status_app
from app.cli.commands.stop import app as stop_app
from app.cli.commands.list_cmd import app as list_app
from app.cli.commands.logs import app as logs_app
from app.cli.commands.deploy import app as deploy_app
from app.cli.commands.scan import app as scan_app
from app.cli.commands.research import app as research_app
from app.cli.commands.health import app as health_app
from app.cli.commands.backup import app as backup_app
from app.cli.commands.update import app as update_app
from app.cli.commands.config_cmd import app as config_app

console = Console()

# ── Root application ─────────────────────────────────────────────────────────

app = typer.Typer(
    name="factory",
    help=(
        "Factory Control Bot — Black Box Software Factory v2.0\n\n"
        "Orchestrates multi-model AI pipelines to build software with "
        "cross-provider verification and information barriers.\n\n"
        "Run [cyan]factory <command> --help[/cyan] for command-specific help."
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)

# ── Register command groups ───────────────────────────────────────────────────

# factory run <project> [options]
app.add_typer(run_app, name="run", help="Start a factory pipeline run.")

# factory status [project]
app.add_typer(status_app, name="status", help="Show factory run status.")

# factory stop <project|run-id>
app.add_typer(stop_app, name="stop", help="Stop a running factory pipeline.")

# factory list [--status ...] [--json]
app.add_typer(list_app, name="list", help="List factory projects.")

# factory logs <project> [--follow] [--lines N]
app.add_typer(logs_app, name="logs", help="View or follow factory run logs.")

# factory deploy <project> [--docker|--manual]
app.add_typer(deploy_app, name="deploy", help="Deploy a completed project.")

# factory scan-models [--verbose] [--force] [--json]
app.add_typer(scan_app, name="scan-models", help="Scan and grade all AI models.")

# factory self-research [--apply] [--dry-run]
app.add_typer(research_app, name="self-research", help="Autonomous codebase self-improvement.")

# factory health [--json]
app.add_typer(health_app, name="health", help="Show system health status.")

# factory backup [--type TYPE] / factory restore <id> / factory list-backups / factory prune
app.add_typer(backup_app, name="backup", help="Database backup and restore.")

# factory update [--engines-only]
app.add_typer(update_app, name="update", help="Update the factory and engine CLIs.")

# factory config sync / factory config show
app.add_typer(config_app, name="config", help="View and verify factory configuration.")


# ── Top-level convenience commands ────────────────────────────────────────────

@app.command(name="version")
def version() -> None:
    """Print the factory version."""
    console.print("[bold]Factory Control Bot[/] v2.0.0")


@app.callback(invoke_without_command=True)
def _root_callback(
    ctx: typer.Context,
    version_flag: bool = typer.Option(
        False, "--version", "-V", is_eager=True, help="Print version and exit"
    ),
) -> None:
    """Factory Control Bot — multi-model AI software pipeline orchestrator."""
    if version_flag:
        console.print("[bold]Factory Control Bot[/] v2.0.0")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point for the factory CLI (registered in pyproject.toml)."""
    app()


if __name__ == "__main__":
    main()
