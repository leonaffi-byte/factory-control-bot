"""Rich panel formatters for structured CLI output."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def health_panel(report: object) -> Panel:
    """
    Build a Rich Panel summarising a HealthReport.

    Args:
        report: HealthReport dataclass instance.

    Returns:
        Rich Panel ready to be printed.
    """
    _STATUS_COLORS = {
        "healthy": "bold green",
        "warning": "bold yellow",
        "critical": "bold red",
        "unknown": "dim",
    }

    overall_status = getattr(report, "overall_status", "unknown")
    timestamp = getattr(report, "timestamp", None)
    metrics = getattr(report, "metrics", [])
    alerts = getattr(report, "alerts", [])

    color = _STATUS_COLORS.get(overall_status, "white")
    ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC") if timestamp else "—"

    lines: list[str] = [
        f"[{color}]Overall: {overall_status.upper()}[/]",
        f"[dim]Checked at: {ts_str}[/]",
        "",
    ]

    for m in metrics:
        m_color = _STATUS_COLORS.get(getattr(m, "status", "unknown"), "white")
        lines.append(
            f"  [{m_color}]{getattr(m, 'name', '?'):22s}[/] "
            f"{getattr(m, 'value', '')} "
            f"[dim]{getattr(m, 'details', '') or ''}[/]"
        )

    if alerts:
        lines.append("\n[bold red]Alerts:[/]")
        for a in alerts:
            sev_color = "red" if getattr(a, "severity", "") == "critical" else "yellow"
            lines.append(
                f"  [{sev_color}][{getattr(a, 'severity', '?').upper()}][/] "
                f"{getattr(a, 'message', '')}"
            )
            rem = getattr(a, "remediation", None)
            if rem:
                lines.append(f"  [dim]  -> {rem}[/]")

    border_color = {
        "healthy": "green",
        "warning": "yellow",
        "critical": "red",
        "unknown": "dim",
    }.get(overall_status, "white")

    return Panel(
        "\n".join(lines),
        title="[bold]System Health[/]",
        border_style=border_color,
        expand=False,
    )


def scan_panel(result: object) -> Panel:
    """
    Build a Rich Panel summarising a ScanResult / SuggestedConfig.

    Args:
        result: ScanResult dataclass instance.

    Returns:
        Rich Panel ready to be printed.
    """
    suggestion = getattr(result, "suggestion", None)
    timestamp = getattr(result, "timestamp", None)
    cached = getattr(result, "cached", False)

    viability = getattr(suggestion, "overall_viability", 0)
    viability_desc = getattr(suggestion, "viability_description", "")
    providers_scanned = getattr(suggestion, "providers_scanned", 0)
    providers_healthy = getattr(suggestion, "providers_healthy", 0)
    scan_duration = getattr(suggestion, "scan_duration_seconds", 0.0)
    recommendations = getattr(suggestion, "recommendations", [])

    viability_color = (
        "green" if viability >= 80
        else "yellow" if viability >= 50
        else "red"
    )

    ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else "—"
    cache_note = " [dim](cached)[/]" if cached else ""

    lines: list[str] = [
        f"[bold]Scan Time:[/] {ts_str}{cache_note}",
        f"[bold]Providers:[/] {providers_healthy}/{providers_scanned} healthy",
        f"[bold]Duration:[/] {scan_duration:.1f}s",
        f"[bold]Viability:[/] [{viability_color}]{viability}/100 — {viability_desc}[/]",
    ]

    if recommendations:
        lines.append("\n[bold]Recommendations:[/]")
        for rec in recommendations:
            lines.append(
                f"  [cyan]{getattr(rec, 'role', '?'):14s}[/] "
                f"[yellow]{getattr(rec, 'provider', '')}[/]/"
                f"{getattr(rec, 'model', '')} "
                f"[dim](score={getattr(rec, 'score', 0):.2f})[/]"
            )

    border_color = (
        "green" if viability >= 80
        else "yellow" if viability >= 50
        else "red"
    )

    return Panel(
        "\n".join(lines),
        title="[bold]Model Scan Results[/]",
        border_style=border_color,
        expand=False,
    )


def cost_panel(
    daily_cost: float,
    run_costs: dict[str, float] | None = None,
    threshold: float | None = None,
) -> Panel:
    """
    Build a Rich Panel showing cost information.

    Args:
        daily_cost: Today's total cost in USD.
        run_costs: Optional dict of run_id -> cost.
        threshold: Budget threshold for visual warning.

    Returns:
        Rich Panel ready to be printed.
    """
    over_budget = threshold is not None and daily_cost >= threshold
    cost_color = "bold red" if over_budget else "bold green"
    threshold_str = f" / ${threshold:.2f} limit" if threshold is not None else ""

    lines: list[str] = [
        f"[bold]Today's Spend:[/] [{cost_color}]${daily_cost:.4f}{threshold_str}[/]",
    ]

    if over_budget:
        lines.append("[bold red]  BUDGET THRESHOLD EXCEEDED[/]")

    if run_costs:
        lines.append("\n[bold]Per-Run Costs:[/]")
        for run_id, cost in sorted(run_costs.items(), key=lambda x: -x[1]):
            lines.append(f"  [cyan]{str(run_id)[:8]}...[/]  ${cost:.4f}")

    return Panel(
        "\n".join(lines),
        title="[bold]Cost Tracker[/]",
        border_style="red" if over_budget else "green",
        expand=False,
    )


def run_panel(run: object) -> Panel:
    """
    Build a Rich Panel showing details of a single factory run.

    Args:
        run: FactoryRun ORM instance.

    Returns:
        Rich Panel ready to be printed.
    """
    _STATUS_COLORS = {
        "running": "green",
        "queued": "blue",
        "completed": "bold green",
        "failed": "red",
        "escalated": "bold red",
        "paused": "yellow",
    }

    status = getattr(run, "status", "unknown")
    color = _STATUS_COLORS.get(status, "white")
    run_id = getattr(run, "id", "?")
    engine = getattr(run, "engine", "?")
    phase = getattr(run, "current_phase", 0)
    started = getattr(run, "started_at", None)
    completed = getattr(run, "completed_at", None)
    cost = float(getattr(run, "total_cost", 0))
    error = getattr(run, "error_message", None)

    lines: list[str] = [
        f"[bold]Run ID:[/]    {run_id}",
        f"[bold]Engine:[/]    {engine}",
        f"[bold]Status:[/]    [{color}]{status}[/]",
        f"[bold]Phase:[/]     {phase}",
        f"[bold]Cost:[/]      ${cost:.4f}",
    ]

    if started:
        lines.append(f"[bold]Started:[/]   {started.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if completed:
        lines.append(f"[bold]Completed:[/] {completed.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if error:
        lines.append(f"\n[bold red]Error:[/] {error}")

    border_style = {
        "running": "green",
        "completed": "green",
        "failed": "red",
        "escalated": "red",
        "paused": "yellow",
    }.get(status, "dim")

    project_name = getattr(run, "project_name", "unknown")
    return Panel(
        "\n".join(lines),
        title=f"[bold]Run: {project_name}[/]",
        border_style=border_style,
        expand=False,
    )
