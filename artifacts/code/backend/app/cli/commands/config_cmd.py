"""CLI command: factory config — configuration management."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(help="Manage factory configuration.")


@app.command()
def sync(
    verify: bool = typer.Option(
        True, "--verify/--no-verify",
        help="Verify all API keys by running health checks after syncing",
    ),
    show_keys: bool = typer.Option(
        False, "--show-keys",
        help="Display masked API key values in the output table",
    ),
) -> None:
    """
    Sync and display the current factory configuration.

    Reads settings from the environment / .env file, shows all configured
    values, and optionally verifies API keys by pinging each provider.
    """

    async def _sync() -> None:
        from app.config import get_settings
        from app.providers.registry import ProviderRegistry

        settings = get_settings()

        # Show configuration table
        table = Table(
            title="Factory Configuration",
            show_lines=False,
            header_style="bold cyan",
        )
        table.add_column("Setting", style="white", min_width=28)
        table.add_column("Value", style="yellow")

        # Core settings
        _add_setting(table, "database_url", settings.database_url, secret=True)
        _add_setting(table, "factory_root_dir", str(settings.factory_root_dir))
        _add_setting(table, "templates_dir", str(settings.templates_dir))
        _add_setting(table, "backup_dir", str(settings.backup_dir))
        _add_setting(table, "default_engine", settings.default_engine)
        _add_setting(table, "default_routing_mode", settings.default_routing_mode)
        _add_setting(table, "quality_gate_threshold", str(settings.quality_gate_threshold))
        _add_setting(table, "max_quality_retries", str(settings.max_quality_retries))
        _add_setting(table, "max_fix_cycles", str(settings.max_fix_cycles))
        _add_setting(table, "cost_alert_threshold", f"${settings.cost_alert_threshold:.2f}")
        _add_setting(table, "log_level", settings.log_level)

        if show_keys:
            masked = settings.get_masked_keys()
            for key, value in masked.items():
                configured = value != "****"
                color = "green" if configured else "dim red"
                table.add_row(key, f"[{color}]{value}[/]")
        else:
            # Just show which keys are configured (not values)
            all_key_fields = [
                "groq_api_key", "openai_api_key", "openrouter_api_key",
                "google_api_key", "perplexity_api_key", "github_token",
                "nvidia_api_key", "together_api_key", "cerebras_api_key",
                "sambanova_api_key", "fireworks_api_key", "mistral_api_key",
            ]
            for field in all_key_fields:
                value = getattr(settings, field, "")
                configured = bool(value)
                status = "[green]configured[/]" if configured else "[dim]not set[/]"
                table.add_row(field, status)

        console.print(table)

        if not verify:
            return

        # Verify API keys via health checks
        console.print("\n[bold]Verifying providers...[/]")
        registry = ProviderRegistry(settings=settings)
        with console.status("Initialising...", spinner="dots"):
            await registry.initialize()

        health_map = await registry.check_health_all()

        verify_table = Table(show_lines=False, header_style="bold cyan")
        verify_table.add_column("Provider", style="white", min_width=18)
        verify_table.add_column("Status", justify="center")
        verify_table.add_column("Latency", justify="right", style="dim")
        verify_table.add_column("Error", style="dim red", max_width=40)

        for provider, h in health_map.items():
            status_str = "[green]healthy[/]" if h.is_healthy else "[red]unhealthy[/]"
            verify_table.add_row(
                provider,
                status_str,
                f"{h.latency_ms}ms" if h.is_healthy else "—",
                h.error or "",
            )

        console.print(verify_table)

    def _add_setting(table: Table, name: str, value: str, secret: bool = False) -> None:
        display = (
            value[:4] + "..." + value[-4:] if secret and len(value) > 12 else value
        )
        table.add_row(name, display)

    try:
        asyncio.run(_sync())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)


@app.command()
def show() -> None:
    """Display all current configuration values (alias for sync --no-verify)."""
    ctx = typer.get_current_context()
    ctx.invoke(sync, verify=False, show_keys=False)
