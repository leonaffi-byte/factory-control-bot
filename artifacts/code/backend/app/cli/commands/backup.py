"""CLI commands: factory backup / factory restore."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(help="Backup and restore the factory database.")


@app.command()
def backup(
    backup_type: str = typer.Option(
        "manual",
        "--type", "-t",
        help="Backup type: manual | daily | weekly | monthly",
    ),
) -> None:
    """Create a database backup."""

    async def _backup() -> None:
        from app.config import get_settings
        from app.database.session import get_session_factory
        from app.services.backup_service import BackupService

        settings = get_settings()
        session_factory = get_session_factory(settings)
        svc = BackupService(session_factory=session_factory)

        with console.status(f"[bold green]Creating {backup_type} backup...", spinner="dots"):
            b = await svc.create_backup(backup_type=backup_type)

        console.print(
            f"[bold green]Backup created![/]\n"
            f"  ID:        {b.id}\n"
            f"  Type:      {b.backup_type}\n"
            f"  File:      {b.file_path}\n"
            f"  Size:      {b.file_size_bytes:,} bytes\n"
            f"  Checksum:  {b.sha256_checksum[:16]}...\n"
            f"  Schema:    {b.schema_version}\n"
            f"  Retention: {b.retention_until}"
        )

    try:
        asyncio.run(_backup())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)


@app.command()
def restore(
    backup_id: int = typer.Argument(..., help="Backup ID to restore"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompt"
    ),
) -> None:
    """Restore the database from a backup by BACKUP_ID."""

    if not force:
        console.print(
            "[bold yellow]Warning:[/] This will overwrite the current database. "
            "A safety snapshot will be created automatically."
        )
        confirmed = typer.confirm(
            f"Restore from backup #{backup_id}?", default=False
        )
        if not confirmed:
            console.print("[dim]Aborted.[/]")
            raise typer.Exit(code=0)

    async def _restore() -> None:
        from app.config import get_settings
        from app.database.session import get_session_factory
        from app.services.backup_service import BackupService

        settings = get_settings()
        session_factory = get_session_factory(settings)
        svc = BackupService(session_factory=session_factory)

        with console.status(f"[bold green]Restoring backup #{backup_id}...", spinner="dots"):
            result = await svc.restore_backup(backup_id=backup_id)

        if result.success:
            console.print(
                f"[bold green]Restore successful![/]\n"
                f"  Backup ID:        {result.backup_id}\n"
                f"  Schema match:     {result.schema_compatible}\n"
                f"  Safety snapshot:  {result.safety_snapshot_path or '—'}"
            )
            if result.warnings:
                for w in result.warnings:
                    console.print(f"  [yellow]Warning:[/] {w}")
        else:
            console.print(f"[bold red]Restore failed:[/] {result.error}")
            raise typer.Exit(code=1)

    try:
        asyncio.run(_restore())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)


@app.command(name="list-backups")
def list_backups() -> None:
    """List all available backups."""

    async def _list() -> None:
        from app.config import get_settings
        from app.database.session import get_session_factory
        from app.services.backup_service import BackupService

        settings = get_settings()
        session_factory = get_session_factory(settings)
        svc = BackupService(session_factory=session_factory)
        backups = await svc.list_backups()

        if not backups:
            console.print("[dim]No backups found.[/]")
            return

        table = Table(title="Database Backups", show_lines=False, header_style="bold cyan")
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

        console.print(table)

    try:
        asyncio.run(_list())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)


@app.command(name="prune")
def prune() -> None:
    """Apply the retention policy and delete expired backups."""

    async def _prune() -> None:
        from app.config import get_settings
        from app.database.session import get_session_factory
        from app.services.backup_service import BackupService

        settings = get_settings()
        session_factory = get_session_factory(settings)
        svc = BackupService(session_factory=session_factory)

        with console.status("Applying retention policy...", spinner="dots"):
            deleted = await svc.apply_retention_policy()

        console.print(f"[bold green]Done![/] Deleted [cyan]{deleted}[/] expired backup(s).")

    try:
        asyncio.run(_prune())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)
