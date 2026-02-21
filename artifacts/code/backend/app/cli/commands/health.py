"""CLI command: factory health — system health report."""

from __future__ import annotations

import asyncio
import json as json_module

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
app = typer.Typer(help="Show system health status.")


@app.command()
def health(
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON"
    ),
) -> None:
    """Display a full system health report: disk, database, providers, memory."""

    async def _health() -> None:
        from app.config import get_settings
        from app.providers.registry import ProviderRegistry
        from app.services.health_monitor import HealthMonitor

        settings = get_settings()
        registry = ProviderRegistry(settings=settings)

        with console.status("Initialising providers...", spinner="dots"):
            await registry.initialize()

        monitor = HealthMonitor(settings=settings, registry=registry)

        with console.status("[bold green]Running health checks...", spinner="dots"):
            report = await monitor.check_health()

        if json_output:
            data = {
                "timestamp": report.timestamp.isoformat(),
                "overall_status": report.overall_status,
                "metrics": [
                    {
                        "name": m.name,
                        "status": m.status,
                        "value": m.value,
                        "details": m.details,
                    }
                    for m in report.metrics
                ],
                "alerts": [
                    {
                        "alert_type": a.alert_type,
                        "severity": a.severity,
                        "message": a.message,
                        "metric_value": a.metric_value,
                        "threshold": a.threshold,
                        "remediation": a.remediation,
                    }
                    for a in report.alerts
                ],
            }
            console.print_json(json_module.dumps(data))
            return

        # Human-readable output
        _STATUS_COLORS = {
            "healthy": "bold green",
            "warning": "bold yellow",
            "critical": "bold red",
            "unknown": "dim",
        }

        overall_color = _STATUS_COLORS.get(report.overall_status, "white")
        console.print(
            Panel(
                f"Overall Status: [{overall_color}]{report.overall_status.upper()}[/]\n"
                f"Checked at: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                title="System Health",
                border_style=overall_color.replace("bold ", ""),
            )
        )

        # Metrics table
        table = Table(show_lines=False, header_style="bold cyan")
        table.add_column("Metric", style="white", min_width=22)
        table.add_column("Status", justify="center", width=10)
        table.add_column("Value", style="yellow", justify="right", width=12)
        table.add_column("Details", style="dim")

        for m in report.metrics:
            color = _STATUS_COLORS.get(m.status, "white")
            table.add_row(
                m.name,
                f"[{color}]{m.status}[/]",
                m.value,
                m.details or "",
            )

        console.print(table)

        # Alerts
        if report.alerts:
            console.print("\n[bold red]Alerts:[/]")
            for alert in report.alerts:
                severity_color = "red" if alert.severity == "critical" else "yellow"
                console.print(
                    f"  [{severity_color}][{alert.severity.upper()}][/] "
                    f"{alert.message}"
                )
                if alert.remediation:
                    console.print(f"  [dim]  Remediation: {alert.remediation}[/]")
        else:
            console.print("\n[dim]No alerts.[/]")

    try:
        asyncio.run(_health())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)
