"""CLI command: factory logs — tail factory run logs."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="View or follow factory run logs.")


@app.command()
def logs(
    project: str = typer.Argument(..., help="Project name"),
    follow: bool = typer.Option(
        False, "--follow", "-f", help="Follow log output (like tail -f)"
    ),
    lines: int = typer.Option(
        50, "--lines", "-n", help="Number of lines to show initially"
    ),
) -> None:
    """
    Print the last N log lines for PROJECT.

    Use --follow / -f to continuously stream new log lines as they appear.
    """

    async def _get_log_path() -> Path | None:
        from app.config import get_settings
        from app.database.session import get_session_factory
        from sqlalchemy import select
        from app.models.factory_run import FactoryRun
        from app.models.project import Project

        settings = get_settings()
        session_factory = get_session_factory(settings)

        async with session_factory() as session:
            sub = select(Project.id).where(Project.name == project)
            result = await session.execute(
                select(FactoryRun)
                .where(FactoryRun.project_id.in_(sub))
                .order_by(FactoryRun.created_at.desc())
                .limit(1)
            )
            run = result.scalar_one_or_none()

        if run is None or not run.log_file_path:
            return None
        return Path(run.log_file_path)

    log_path = asyncio.run(_get_log_path())

    if log_path is None:
        console.print(
            f"[bold red]Error:[/] No active run or log file found for project '{project}'."
        )
        raise typer.Exit(code=1)

    if not log_path.exists():
        console.print(f"[dim]Log file not yet created:[/] {log_path}")
        if not follow:
            raise typer.Exit(code=0)

    # Print last N lines
    if log_path.exists():
        content = log_path.read_text(errors="replace").splitlines()
        tail = content[-lines:] if len(content) > lines else content
        for line in tail:
            console.print(line, highlight=False)

    if not follow:
        return

    # Follow mode: poll for new content
    console.print(f"[dim]--- Following {log_path} (Ctrl-C to stop) ---[/]")
    last_pos = log_path.stat().st_size if log_path.exists() else 0

    try:
        while True:
            time.sleep(2)
            if not log_path.exists():
                continue
            current_size = log_path.stat().st_size
            if current_size > last_pos:
                with open(log_path, errors="replace") as f:
                    f.seek(last_pos)
                    new_content = f.read()
                    last_pos = f.tell()
                for line in new_content.splitlines():
                    console.print(line, highlight=False)
            elif current_size < last_pos:
                # File was rotated
                last_pos = 0
    except KeyboardInterrupt:
        console.print("\n[dim]Log follow stopped.[/]")
