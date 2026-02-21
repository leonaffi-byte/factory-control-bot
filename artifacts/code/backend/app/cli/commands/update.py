"""CLI command: factory update — update the factory itself."""

from __future__ import annotations

import asyncio
import subprocess
import sys

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Update the factory and its AI engine CLIs.")


@app.command()
def update(
    engines_only: bool = typer.Option(
        False,
        "--engines-only",
        help="Only update AI engine CLIs, not the factory itself",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be updated without running it"
    ),
) -> None:
    """
    Update the factory application and/or AI engine CLI tools.

    Without --engines-only, this runs:
      1. git pull (update factory source)
      2. pip install -e . (update Python dependencies)
      3. alembic upgrade head (apply DB migrations)

    With --engines-only, only the AI CLI tools are updated.
    """

    async def _update() -> None:
        import shutil

        steps: list[tuple[str, list[str]]] = []

        if not engines_only:
            steps += [
                ("Pull latest factory source", ["git", "pull", "--ff-only"]),
                (
                    "Update Python dependencies",
                    [sys.executable, "-m", "pip", "install", "-e", ".", "--quiet"],
                ),
                ("Apply database migrations", ["alembic", "upgrade", "head"]),
            ]

        # Detect installed engine CLIs and update them
        engine_update_cmds: dict[str, list[str]] = {
            "claude": ["npm", "install", "-g", "@anthropic-ai/claude-code@latest"],
            "gemini": ["npm", "install", "-g", "@google/gemini-cli@latest"],
            "aider": [sys.executable, "-m", "pip", "install", "-U", "aider-chat"],
        }

        for engine, cmd in engine_update_cmds.items():
            binary = shutil.which(engine) or shutil.which(cmd[0])
            if binary:
                steps.append((f"Update {engine} CLI", cmd))
            else:
                console.print(f"[dim]  Skipping {engine}: not installed.[/]")

        if not steps:
            console.print("[dim]Nothing to update.[/]")
            return

        for description, cmd in steps:
            if dry_run:
                console.print(f"[dim]  (dry run) {description}: {' '.join(cmd)}[/]")
                continue

            console.print(f"[bold]  {description}...[/]")
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=_factory_root()
            )
            if result.returncode == 0:
                console.print(f"  [green]OK[/]")
            else:
                console.print(
                    f"  [red]FAILED (exit {result.returncode})[/]\n"
                    f"  {result.stderr.strip()[:300]}"
                )

        if not dry_run:
            console.print("\n[bold green]Update complete![/]")
        else:
            console.print("\n[dim]Dry run complete — no changes made.[/]")

    def _factory_root() -> str:
        from pathlib import Path
        return str(Path(__file__).resolve().parents[4])

    try:
        asyncio.run(_update())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)
