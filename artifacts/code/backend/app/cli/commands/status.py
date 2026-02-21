"""CLI command: factory status — show project/run status."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(help="Show status of factory runs.")


@app.command()
def status(
    project: Optional[str] = typer.Argument(
        None, help="Project name to filter by (omit for all active runs)"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON"
    ),
) -> None:
    """Show the status of factory runs, optionally filtered by PROJECT."""

    async def _status() -> None:
        import json as json_module

        from app.config import get_settings
        from app.database.session import get_session_factory
        from app.services.project_service import ProjectService
        from app.services.run_monitor import RunMonitor

        settings = get_settings()
        session_factory = get_session_factory(settings)

        from sqlalchemy import select
        from app.models.factory_run import FactoryRun

        async with session_factory() as session:
            query = select(FactoryRun).order_by(FactoryRun.created_at.desc()).limit(50)
            if project:
                from app.models.project import Project
                sub = select(Project.id).where(Project.name == project)
                query = query.where(FactoryRun.project_id.in_(sub))
            result = await session.execute(query)
            runs = list(result.scalars().all())

        if json_output:
            data = [
                {
                    "id": str(r.id),
                    "project_id": str(r.project_id),
                    "engine": r.engine,
                    "status": r.status,
                    "phase": r.current_phase,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                }
                for r in runs
            ]
            console.print_json(json_module.dumps(data))
            return

        if not runs:
            console.print("[dim]No runs found.[/]")
            return

        table = Table(title="Factory Runs", show_lines=True)
        table.add_column("Run ID", style="cyan", no_wrap=True, max_width=12)
        table.add_column("Project", style="white")
        table.add_column("Engine", style="yellow")
        table.add_column("Phase", justify="center")
        table.add_column("Status", justify="center")
        table.add_column("Started At", style="dim")

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
            started = (
                r.started_at.strftime("%Y-%m-%d %H:%M") if r.started_at else "—"
            )
            table.add_row(
                str(r.id)[:8] + "...",
                r.project_name,
                r.engine,
                str(r.current_phase),
                f"[{color}]{r.status}[/]",
                started,
            )

        console.print(table)

    try:
        asyncio.run(_status())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)
