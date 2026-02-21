"""CLI command: factory list — list projects."""

from __future__ import annotations

import asyncio
import json as json_module
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(help="List factory projects.")


@app.command(name="list")
def list_projects(
    status: Optional[str] = typer.Option(
        None, "--status", "-s",
        help="Filter by status: draft | queued | running | completed | failed",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON"
    ),
    limit: int = typer.Option(
        20, "--limit", "-n", help="Maximum number of projects to show"
    ),
) -> None:
    """List all factory projects, optionally filtered by STATUS."""

    async def _list() -> None:
        from app.config import get_settings
        from app.database.session import get_session_factory
        from app.services.project_service import ProjectService

        settings = get_settings()
        session_factory = get_session_factory(settings)
        project_service = ProjectService(session_factory=session_factory)

        projects, total = await project_service.list_projects(
            offset=0,
            limit=limit,
            status_filter=status,
        )

        if json_output:
            data = [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "status": p.status,
                    "engines": p.engines,
                    "total_cost": float(p.total_cost or 0),
                    "created_at": p.created_at.isoformat(),
                }
                for p in projects
            ]
            console.print_json(json_module.dumps({"projects": data, "total": total}))
            return

        if not projects:
            console.print("[dim]No projects found.[/]")
            return

        table = Table(
            title=f"Projects ({total} total)",
            show_lines=False,
            header_style="bold cyan",
        )
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

        console.print(table)
        if total > limit:
            console.print(f"[dim]Showing {limit} of {total}. Use --limit to see more.[/]")

    try:
        asyncio.run(_list())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)
