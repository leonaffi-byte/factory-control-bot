"""CLI command: factory deploy — deploy a completed project."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()
app = typer.Typer(help="Deploy a completed factory project.")


@app.command()
def deploy(
    project: str = typer.Argument(..., help="Project name to deploy"),
    docker: bool = typer.Option(
        False, "--docker", help="Deploy using Docker Compose"
    ),
    manual: bool = typer.Option(
        False, "--manual", help="Show manual deployment instructions"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be deployed without executing"
    ),
) -> None:
    """Deploy project PROJECT using Docker or manual instructions."""

    async def _deploy() -> None:
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

        if project_obj.status not in ("completed", "deployed"):
            console.print(
                f"[bold yellow]Warning:[/] Project is in status "
                f"'{project_obj.status}'. Only 'completed' projects can be deployed."
            )
            if not typer.confirm("Deploy anyway?", default=False):
                raise typer.Exit(code=0)

        deploy_config = project_obj.deploy_config or {}
        deploy_type = deploy_config.get("type", "unknown")

        if dry_run:
            console.print(
                Panel(
                    f"[bold]Project:[/] {project}\n"
                    f"[bold]Deploy type:[/] {deploy_type}\n"
                    f"[bold]Config:[/] {deploy_config}\n"
                    f"[dim]Dry run — no changes made.[/]",
                    title="Deployment Preview",
                    border_style="yellow",
                )
            )
            return

        if docker:
            await _docker_deploy(project, project_obj)
        elif manual:
            _show_manual_instructions(project, deploy_config)
        else:
            # Auto-detect
            if docker or deploy_config.get("target") == "local_docker":
                await _docker_deploy(project, project_obj)
            else:
                _show_manual_instructions(project, deploy_config)

    async def _docker_deploy(project_name: str, project_obj: object) -> None:
        """Run docker-compose up for the project."""
        import subprocess

        from app.config import get_settings
        settings = get_settings()
        project_dir = settings.factory_root_dir / f"{project_name}-{project_obj.engines[0] if project_obj.engines else 'claude'}"  # type: ignore[attr-defined]
        compose_file = project_dir / "docker-compose.yml"

        if not compose_file.exists():
            compose_file = project_dir / "artifacts" / "release" / "docker-compose.yml"

        if not compose_file.exists():
            console.print(
                f"[bold red]Error:[/] No docker-compose.yml found in {project_dir}"
            )
            raise typer.Exit(code=1)

        console.print(f"[bold green]Deploying[/] {project_name} with Docker Compose...")
        console.print(f"[dim]compose file: {compose_file}[/]")

        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "up", "-d", "--build"],
            capture_output=False,
        )
        if result.returncode == 0:
            console.print("[bold green]Deployment successful![/]")
        else:
            console.print(f"[bold red]Deployment failed.[/] Exit code: {result.returncode}")
            raise typer.Exit(code=result.returncode)

    def _show_manual_instructions(project_name: str, deploy_config: dict) -> None:
        console.print(
            Panel(
                f"[bold]Manual Deployment Steps for '{project_name}'[/]\n\n"
                "1. Navigate to the project artifacts/release/ directory\n"
                "2. Review DEPLOYMENT.md for full instructions\n"
                "3. Run the deploy.sh script: [cyan]bash deploy.sh[/]\n"
                "   or follow the manual steps in DEPLOYMENT.md\n\n"
                f"[dim]Deploy config: {deploy_config}[/]",
                title="Manual Deployment",
                border_style="cyan",
            )
        )

    try:
        asyncio.run(_deploy())
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1)
