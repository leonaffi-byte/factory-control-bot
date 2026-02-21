"""Rich table helper functions for consistent CLI output formatting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.table import Table

if TYPE_CHECKING:
    pass


def project_table(projects: list) -> Table:
    """
    Build a Rich Table for a list of Project ORM objects.

    Columns: Name | Status | Engines | Cost | Created
    """
    table = Table(title="Projects", show_lines=False, header_style="bold cyan")
    table.add_column("Name", style="bold white", min_width=15)
    table.add_column("Status", justify="center")
    table.add_column("Engines", style="dim")
    table.add_column("Cost (USD)", justify="right", style="yellow")
    table.add_column("Created", style="dim")

    _STATUS_COLORS = {
        "draft": "dim",
        "queued": "blue",
        "running": "green",
        "completed": "bold green",
        "failed": "red",
        "deployed": "bold cyan",
    }

    for p in projects:
        color = _STATUS_COLORS.get(p.status, "white")
        engines_str = ", ".join(p.engines or []) or "—"
        cost_str = f"${float(p.total_cost or 0):.2f}"
        created = p.created_at.strftime("%Y-%m-%d")

        table.add_row(
            p.name,
            f"[{color}]{p.status}[/]",
            engines_str,
            cost_str,
            created,
        )

    return table


def run_table(runs: list) -> Table:
    """
    Build a Rich Table for a list of FactoryRun ORM objects.

    Columns: Run ID | Project | Engine | Phase | Status | Started
    """
    table = Table(title="Factory Runs", show_lines=True, header_style="bold cyan")
    table.add_column("Run ID", style="cyan", no_wrap=True, max_width=12)
    table.add_column("Project", style="white")
    table.add_column("Engine", style="yellow")
    table.add_column("Phase", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Cost", justify="right", style="dim")
    table.add_column("Started", style="dim")

    _STATUS_COLORS = {
        "running": "green",
        "queued": "blue",
        "completed": "bold green",
        "failed": "red",
        "escalated": "bold red",
        "paused": "yellow",
    }

    for r in runs:
        color = _STATUS_COLORS.get(r.status, "white")
        started = r.started_at.strftime("%Y-%m-%d %H:%M") if r.started_at else "—"
        cost = f"${float(r.total_cost or 0):.2f}"

        table.add_row(
            str(r.id)[:8] + "…",
            getattr(r, "project_name", str(r.project_id)[:8]),
            r.engine,
            str(r.current_phase),
            f"[{color}]{r.status}[/]",
            cost,
            started,
        )

    return table


def provider_table(providers: list, health_map: dict | None = None) -> Table:
    """
    Build a Rich Table for a list of ProviderInfo dataclasses.

    Columns: Name | Type | Free? | Healthy | Latency | Models
    """
    table = Table(title="Providers", show_lines=False, header_style="bold cyan")
    table.add_column("Name", style="white", min_width=18)
    table.add_column("Adapter", style="dim")
    table.add_column("Free?", justify="center")
    table.add_column("Enabled?", justify="center")
    table.add_column("Healthy?", justify="center")
    table.add_column("Latency", justify="right", style="dim")
    table.add_column("Last Check", style="dim")

    health_map = health_map or {}

    for p in providers:
        free_str = "[green]yes[/]" if p.is_free else "[dim]no[/]"
        enabled_str = "[green]yes[/]" if p.is_enabled else "[red]no[/]"
        health = health_map.get(p.name)
        if health is not None:
            healthy_str = "[green]yes[/]" if health.is_healthy else "[red]no[/]"
            latency_str = f"{health.latency_ms}ms" if health.is_healthy else "—"
        else:
            healthy_str = "[dim]?[/]"
            latency_str = "—"

        last_check = (
            p.last_health_check.strftime("%H:%M:%S")
            if p.last_health_check
            else "—"
        )

        table.add_row(
            p.display_name,
            p.adapter_type,
            free_str,
            enabled_str,
            healthy_str,
            latency_str,
            last_check,
        )

    return table


def backup_table(backups: list) -> Table:
    """
    Build a Rich Table for a list of Backup ORM objects.

    Columns: ID | Type | Status | Size | Schema | Retain Until | Created
    """
    table = Table(title="Backups", show_lines=False, header_style="bold cyan")
    table.add_column("ID", justify="right", width=5)
    table.add_column("Type", style="yellow")
    table.add_column("Status", justify="center")
    table.add_column("Size", justify="right", style="dim")
    table.add_column("Schema", style="dim")
    table.add_column("Retain Until", style="dim")
    table.add_column("Created", style="dim")

    for b in backups:
        size_mb = b.file_size_bytes / (1024 * 1024)
        table.add_row(
            str(b.id),
            b.backup_type,
            b.status,
            f"{size_mb:.1f} MB",
            b.schema_version,
            str(b.retention_until or "—"),
            b.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    return table


def grade_table(grades: list) -> Table:
    """
    Build a Rich Table for a list of ModelGrade dataclasses.

    Columns: Provider | Model | Overall | Quality | Avail. | Context | Speed
    """
    table = Table(title="Model Grades", show_lines=False, header_style="bold magenta")
    table.add_column("Provider", style="yellow")
    table.add_column("Model", style="cyan")
    table.add_column("Overall", justify="right")
    table.add_column("Quality", justify="right")
    table.add_column("Avail.", justify="center")
    table.add_column("Context", justify="right", style="dim")
    table.add_column("Speed", justify="right", style="dim")

    for g in sorted(grades, key=lambda x: x.overall_score, reverse=True):
        avail_str = "[green]yes[/]" if g.is_available else "[red]no[/]"
        table.add_row(
            g.provider,
            g.model,
            f"{g.overall_score:.2f}",
            f"{g.quality_score:.2f}",
            avail_str,
            f"{g.context_window // 1000}k",
            f"{g.speed_score:.2f}",
        )

    return table
