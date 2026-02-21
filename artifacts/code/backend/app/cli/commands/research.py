"""CLI command: factory self-research — autonomous codebase improvement."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(help="Run self-research on the factory codebase.")


@app.command(name="self-research")
def self_research(
    apply: bool = typer.Option(
        False, "--apply", help="Auto-apply all low-risk suggestions"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Run analysis but do not apply any changes"
    ),
    suggestion_id: int = typer.Option(
        0, "--apply-id", help="Apply a specific suggestion by ID"
    ),
) -> None:
    """
    Analyse the factory codebase for improvements and optionally apply suggestions.

    Without flags, runs the full analysis and prints suggestions.
    Use --apply to automatically apply all low-risk suggestions.
    Use --apply-id N to apply a single suggestion by its database ID.
    """

    async def _research() -> None:
        from app.config import get_settings
        from app.database.session import get_session_factory
        from app.providers.rate_limiter import ProviderRateLimiter
        from app.providers.registry import ProviderRegistry
        from app.services.model_router import ModelRouter
        from app.services.self_researcher import SelfResearcher

        settings = get_settings()
        session_factory = get_session_factory(settings)

        registry = ProviderRegistry(settings=settings)
        with console.status("Initialising providers...", spinner="dots"):
            await registry.initialize()

        rate_limiter = ProviderRateLimiter()
        model_router = ModelRouter(registry=registry, rate_limiter=rate_limiter)
        researcher = SelfResearcher(
            session_factory=session_factory,
            model_router=model_router,
        )

        if suggestion_id > 0:
            # Apply a specific suggestion
            console.print(f"Applying suggestion [cyan]{suggestion_id}[/]...")
            if not dry_run:
                result = await researcher.apply_suggestion(suggestion_id)
                if result.success:
                    console.print(
                        f"[bold green]Applied![/] Branch: [cyan]{result.branch_name}[/]"
                    )
                else:
                    console.print(f"[bold red]Failed:[/] {result.error}")
            else:
                console.print(f"[dim]Dry run — would apply suggestion {suggestion_id}.[/]")
            return

        with console.status("[bold green]Running self-research analysis...", spinner="dots"):
            report = await researcher.run_research(triggered_by="cli")

        suggestions = report.suggestions if report.suggestions else []
        console.print(
            f"\n[bold]Self-Research Report #{report.id}[/]\n"
            f"  Triggered by: {report.triggered_by}\n"
            f"  Suggestions: {len(suggestions)}\n"
        )

        if not suggestions:
            console.print("[dim]No suggestions generated.[/]")
            return

        table = Table(title="Improvement Suggestions", show_lines=True, header_style="bold cyan")
        table.add_column("ID", justify="right", style="dim", width=5)
        table.add_column("Category", style="yellow")
        table.add_column("Risk", justify="center")
        table.add_column("Title", style="white", max_width=40)
        table.add_column("Impact", style="dim", max_width=40)

        _RISK_COLORS = {"low": "green", "medium": "yellow", "high": "red"}

        for sug in suggestions:
            risk_color = _RISK_COLORS.get(sug.risk_level, "white")
            table.add_row(
                str(sug.id),
                sug.category,
                f"[{risk_color}]{sug.risk_level}[/]",
                sug.title,
                sug.expected_impact,
            )

        console.print(table)

        if apply and not dry_run:
            low_risk = [s for s in suggestions if s.risk_level == "low"]
            console.print(
                f"\n[bold green]Auto-applying {len(low_risk)} low-risk suggestions...[/]"
            )
            for sug in low_risk:
                result = await researcher.apply_suggestion(sug.id)
                status = "[green]OK[/]" if result.success else f"[red]FAIL: {result.error}[/]"
                console.print(f"  #{sug.id} {sug.title[:50]}: {status}")
        elif apply and dry_run:
            low_risk = [s for s in suggestions if s.risk_level == "low"]
            console.print(
                f"\n[dim]Dry run — would apply {len(low_risk)} low-risk suggestions.[/]"
            )
        else:
            console.print(
                "\n[dim]Use --apply to apply low-risk suggestions, "
                "or --apply-id N for a specific one.[/]"
            )

    try:
        asyncio.run(_research())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)
