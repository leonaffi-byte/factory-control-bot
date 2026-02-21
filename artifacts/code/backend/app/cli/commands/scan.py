"""CLI command: factory scan-models — scan and grade all providers/models."""

from __future__ import annotations

import asyncio
import json as json_module

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(help="Scan and grade all available AI models.")


@app.command(name="scan-models")
def scan_models(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show per-model grades"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Bypass cache and re-probe all providers"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON"
    ),
) -> None:
    """Scan all configured AI providers, probe their models, and suggest configuration."""

    async def _scan() -> None:
        from app.config import get_settings
        from app.providers.registry import ProviderRegistry
        from app.services.model_scanner import ModelScanner

        settings = get_settings()
        registry = ProviderRegistry(settings=settings)

        with console.status("[bold green]Initialising providers...", spinner="dots"):
            await registry.initialize()

        scanner = ModelScanner(registry=registry)

        with console.status("[bold green]Scanning models...", spinner="dots"):
            result = await scanner.scan_all(force=force)

        suggestion = result.suggestion

        if json_output:
            data = {
                "timestamp": result.timestamp.isoformat(),
                "cached": result.cached,
                "overall_viability": suggestion.overall_viability,
                "viability_description": suggestion.viability_description,
                "providers_scanned": suggestion.providers_scanned,
                "providers_healthy": suggestion.providers_healthy,
                "scan_duration_seconds": suggestion.scan_duration_seconds,
                "recommendations": [
                    {
                        "role": r.role,
                        "provider": r.provider,
                        "model": r.model,
                        "score": r.score,
                        "reason": r.reason,
                    }
                    for r in suggestion.recommendations
                ],
                "grades": [
                    {
                        "provider": g.provider,
                        "model": g.model,
                        "overall_score": g.overall_score,
                        "is_available": g.is_available,
                        "context_window": g.context_window,
                    }
                    for g in result.grades
                ] if verbose else [],
            }
            console.print_json(json_module.dumps(data))
            return

        # Human-readable output
        viability_color = (
            "green" if suggestion.overall_viability >= 80
            else "yellow" if suggestion.overall_viability >= 50
            else "red"
        )

        console.print(
            f"\n[bold]Scan Complete[/] "
            f"({'[dim]from cache[/]' if result.cached else 'fresh probe'})\n"
            f"  Providers scanned: {suggestion.providers_scanned} "
            f"({suggestion.providers_healthy} healthy)\n"
            f"  Duration: {suggestion.scan_duration_seconds:.1f}s\n"
            f"  Overall viability: [{viability_color}]{suggestion.overall_viability}/100[/]\n"
            f"  {suggestion.viability_description}\n"
        )

        # Recommendations table
        if suggestion.recommendations:
            rec_table = Table(title="Role Recommendations", show_lines=False, header_style="bold cyan")
            rec_table.add_column("Role", style="white", min_width=14)
            rec_table.add_column("Provider", style="yellow")
            rec_table.add_column("Model", style="cyan")
            rec_table.add_column("Score", justify="right")
            rec_table.add_column("Reason", style="dim", max_width=50)

            for rec in suggestion.recommendations:
                rec_table.add_row(
                    rec.role,
                    rec.provider,
                    rec.model,
                    f"{rec.score:.2f}",
                    rec.reason,
                )
            console.print(rec_table)

        # Verbose: per-model grades
        if verbose and result.grades:
            grade_table = Table(title="Model Grades", show_lines=False, header_style="bold magenta")
            grade_table.add_column("Provider", style="yellow")
            grade_table.add_column("Model", style="cyan")
            grade_table.add_column("Overall", justify="right")
            grade_table.add_column("Quality", justify="right")
            grade_table.add_column("Avail.", justify="right")
            grade_table.add_column("Context", justify="right")
            grade_table.add_column("Speed", justify="right")

            for g in sorted(result.grades, key=lambda x: x.overall_score, reverse=True):
                avail_str = "[green]yes[/]" if g.is_available else "[red]no[/]"
                grade_table.add_row(
                    g.provider,
                    g.model,
                    f"{g.overall_score:.2f}",
                    f"{g.quality_score:.2f}",
                    avail_str,
                    f"{g.context_window // 1000}k",
                    f"{g.speed_score:.2f}",
                )
            console.print(grade_table)

    try:
        asyncio.run(_scan())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)
