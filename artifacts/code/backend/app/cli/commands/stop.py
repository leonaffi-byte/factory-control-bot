"""CLI command: factory stop — stop a running pipeline."""

from __future__ import annotations

import asyncio
from uuid import UUID

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Stop a running factory pipeline.")


@app.command()
def stop(
    target: str = typer.Argument(
        ..., help="Project name or Run UUID to stop"
    ),
    reason: str = typer.Option(
        "Stopped via CLI",
        "--reason", "-r",
        help="Reason for stopping the run",
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Stop a running factory run identified by PROJECT name or RUN_ID."""

    if not force:
        confirmed = typer.confirm(
            f"Are you sure you want to stop '{target}'?", default=False
        )
        if not confirmed:
            console.print("[dim]Aborted.[/]")
            raise typer.Exit(code=0)

    async def _stop() -> None:
        from app.config import get_settings
        from app.database.session import get_session_factory
        from app.providers.rate_limiter import ProviderRateLimiter
        from app.providers.registry import ProviderRegistry
        from app.services.factory_orchestrator import FactoryOrchestrator
        from app.services.model_router import ModelRouter

        settings = get_settings()
        session_factory = get_session_factory(settings)

        # Resolve run_id
        run_id: UUID | None = None
        try:
            run_id = UUID(target)
        except ValueError:
            # Treat as project name — find the latest active run
            from sqlalchemy import select
            from app.models.factory_run import FactoryRun
            from app.models.project import Project

            async with session_factory() as session:
                sub = select(Project.id).where(Project.name == target)
                result = await session.execute(
                    select(FactoryRun)
                    .where(
                        FactoryRun.project_id.in_(sub),
                        FactoryRun.status.in_(["running", "queued", "paused"]),
                    )
                    .order_by(FactoryRun.created_at.desc())
                    .limit(1)
                )
                run = result.scalar_one_or_none()
                if run is None:
                    console.print(
                        f"[bold red]Error:[/] No active run found for project '{target}'."
                    )
                    raise typer.Exit(code=1)
                run_id = run.id

        registry = ProviderRegistry(settings=settings)
        await registry.initialize()
        rate_limiter = ProviderRateLimiter()
        model_router = ModelRouter(registry=registry, rate_limiter=rate_limiter)

        orchestrator = FactoryOrchestrator(
            session_factory=session_factory,
            model_router=model_router,
        )

        await orchestrator.stop_pipeline(run_id, reason=reason)  # type: ignore[arg-type]
        console.print(
            f"[bold green]Stopped[/] run [cyan]{run_id}[/] (reason: {reason})"
        )

    try:
        asyncio.run(_stop())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)
