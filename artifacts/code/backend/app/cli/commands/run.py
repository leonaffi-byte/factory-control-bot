"""CLI command: factory run — start a factory pipeline run."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Start a factory run for a project.")


@app.command()
def run(
    project: str = typer.Argument(..., help="Project name or ID"),
    engine: str = typer.Option(
        "claude",
        "--engine", "-e",
        help="Engine to use: claude | gemini | opencode | aider",
    ),
    tier: int = typer.Option(
        0,
        "--tier", "-t",
        help="Complexity tier (0 = auto-detect, 1-3 = manual override)",
    ),
    free_only: bool = typer.Option(
        True,
        "--free-only/--allow-paid",
        help="Restrict to free model providers only",
    ),
    interface_source: str = typer.Option(
        "cli",
        "--source",
        help="Interface source tag (cli | telegram | api)",
        hidden=True,
    ),
) -> None:
    """Start a factory pipeline run for PROJECT."""
    console.print(
        f"[bold green]Starting factory run[/] for project "
        f"[cyan]{project}[/] (engine=[yellow]{engine}[/], "
        f"tier=[magenta]{'auto' if tier == 0 else tier}[/], "
        f"free_only=[blue]{free_only}[/])"
    )

    async def _run() -> None:
        from app.config import get_settings
        from app.database.session import get_session_factory
        from app.services.project_service import ProjectService

        settings = get_settings()
        session_factory = get_session_factory(settings)
        project_service = ProjectService(session_factory=session_factory)

        project_obj = await project_service.get_project_by_name(project)
        if project_obj is None:
            console.print(f"[bold red]Error:[/] Project '{project}' not found.")
            raise typer.Exit(code=1)

        from app.providers.registry import ProviderRegistry
        from app.providers.rate_limiter import ProviderRateLimiter
        from app.services.factory_orchestrator import FactoryOrchestrator
        from app.services.model_router import ModelRouter

        registry = ProviderRegistry(settings=settings)
        await registry.initialize()

        rate_limiter = ProviderRateLimiter()
        model_router = ModelRouter(registry=registry, rate_limiter=rate_limiter)

        orchestrator = FactoryOrchestrator(
            session_factory=session_factory,
            model_router=model_router,
        )

        run_obj = await orchestrator.start_pipeline(
            project=project_obj,
            engine=engine,
            tier=tier,
            interface_source=interface_source,
        )

        console.print(
            f"[bold green]Run started![/] Run ID: [cyan]{run_obj.id}[/]"
        )

    try:
        asyncio.run(_run())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)
