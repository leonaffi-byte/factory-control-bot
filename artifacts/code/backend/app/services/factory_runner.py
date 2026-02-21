"""Factory runner service — start/stop factory runs, tmux session management."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import select, update

from app.models.factory_run import FactoryRun, RunStatus
from app.models.project import Project

if TYPE_CHECKING:
    from app.config import Settings
    from app.database.session import AsyncSessionFactory

logger = structlog.get_logger()

# Engine start commands
ENGINE_COMMANDS = {
    "claude": "claude --dangerously-skip-permissions /factory",
    "gemini": "gemini",
    "opencode": "opencode",
    "aider": "aider --yes",
}

# Engine config files to copy
ENGINE_CONFIGS = {
    "claude": "CLAUDE.md",
    "gemini": "GEMINI.md",
    "opencode": "OPENCODE.md",
    "aider": ".aider.conf.yml",
}


class FactoryRunner:
    """Manages factory run lifecycle: create, start, stop, pause runs via tmux."""

    def __init__(
        self,
        settings: "Settings",
        session_factory: "AsyncSessionFactory",
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._factory_root = settings.factory_root_dir
        self._templates_dir = settings.templates_dir

    async def start_run(
        self,
        project: Project,
        engine: str,
        created_by: int,
    ) -> FactoryRun:
        """
        Start a factory run:
        1. Create project directory
        2. Copy engine config template
        3. Write raw-input.md with requirements
        4. Create tmux session
        5. Start factory command in tmux
        6. Record run in database
        """
        project_dir = self._factory_root / f"{project.name}-{engine}"
        session_name = f"{project.name}-{engine}"

        # 1. Create project directory structure
        await self._create_project_dir(project_dir)

        # 2. Copy engine config
        await self._copy_engine_config(engine, project_dir)

        # 3. Write requirements
        await self._write_requirements(project, project_dir)

        # 4. Create tmux session and start factory
        await self._start_tmux_session(session_name, project_dir, engine)

        # 5. Record in database
        async with self._session_factory() as session:
            run = FactoryRun(
                project_id=project.id,
                engine=engine,
                status=RunStatus.RUNNING.value,
                current_phase=0,
                tmux_session=session_name,
                project_dir=str(project_dir),
                started_at=datetime.utcnow(),
                created_by=created_by,
            )
            session.add(run)
            await session.flush()
            await session.refresh(run)

            logger.info(
                "factory_run_started",
                run_id=str(run.id),
                project=project.name,
                engine=engine,
                project_dir=str(project_dir),
            )
            return run

    async def stop_run(self, run_id: UUID) -> None:
        """
        Stop a factory run:
        1. Touch .factory-stop file
        2. Wait for graceful shutdown
        3. Kill tmux session if still running
        4. Update DB status
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(FactoryRun).where(FactoryRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run:
                raise ValueError(f"Run {run_id} not found")

        # Touch stop file
        if run.project_dir:
            stop_file = Path(run.project_dir) / ".factory-stop"
            stop_file.touch()

        # Wait for graceful shutdown
        await asyncio.sleep(5)

        # Kill tmux session
        if run.tmux_session:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "tmux", "kill-session", "-t", run.tmux_session,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            except Exception as e:
                logger.warning("tmux_kill_failed", session=run.tmux_session, error=str(e))

        # Update DB
        await self.mark_run_failed(run_id, reason="Stopped by user")

    async def pause_run(self, run_id: UUID) -> None:
        """Touch .factory-pause file. Factory pauses after current phase."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(FactoryRun).where(FactoryRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run or not run.project_dir:
                raise ValueError(f"Run {run_id} not found or no project dir")

        pause_file = Path(run.project_dir) / ".factory-pause"
        pause_file.touch()

        async with self._session_factory() as session:
            await session.execute(
                update(FactoryRun)
                .where(FactoryRun.id == run_id)
                .values(status=RunStatus.PAUSED.value)
            )

        logger.info("factory_run_paused", run_id=str(run_id))

    async def get_active_runs(self) -> list[FactoryRun]:
        """Get all runs with status 'running'."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(FactoryRun).where(FactoryRun.status == RunStatus.RUNNING.value)
            )
            return list(result.scalars().all())

    async def get_run(self, run_id: UUID) -> FactoryRun | None:
        """Get a single run by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(FactoryRun).where(FactoryRun.id == run_id)
            )
            return result.scalar_one_or_none()

    async def get_runs_for_project(self, project_id: UUID) -> list[FactoryRun]:
        """Get all runs for a project."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(FactoryRun)
                .where(FactoryRun.project_id == project_id)
                .order_by(FactoryRun.created_at.desc())
            )
            return list(result.scalars().all())

    async def mark_run_failed(self, run_id: UUID, reason: str = "") -> None:
        """Mark a run as failed."""
        async with self._session_factory() as session:
            await session.execute(
                update(FactoryRun)
                .where(FactoryRun.id == run_id)
                .values(
                    status=RunStatus.FAILED.value,
                    completed_at=datetime.utcnow(),
                    error_message=reason,
                )
            )
        logger.info("factory_run_marked_failed", run_id=str(run_id), reason=reason)

    async def mark_run_completed(self, run_id: UUID) -> None:
        """Mark a run as completed."""
        async with self._session_factory() as session:
            await session.execute(
                update(FactoryRun)
                .where(FactoryRun.id == run_id)
                .values(
                    status=RunStatus.COMPLETED.value,
                    completed_at=datetime.utcnow(),
                )
            )
        logger.info("factory_run_completed", run_id=str(run_id))

    async def update_run_phase(self, run_id: UUID, phase: int) -> None:
        """Update the current phase of a run."""
        async with self._session_factory() as session:
            await session.execute(
                update(FactoryRun)
                .where(FactoryRun.id == run_id)
                .values(current_phase=phase)
            )

    async def update_run_cost(self, run_id: UUID, amount: float, provider: str) -> None:
        """Update the cost of a run."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(FactoryRun).where(FactoryRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if run:
                new_total = float(run.total_cost or 0) + amount
                cost_by_provider = dict(run.cost_by_provider or {})
                cost_by_provider[provider] = cost_by_provider.get(provider, 0) + amount

                await session.execute(
                    update(FactoryRun)
                    .where(FactoryRun.id == run_id)
                    .values(
                        total_cost=new_total,
                        cost_by_provider=cost_by_provider,
                    )
                )

    async def update_log_offset(self, run_id: UUID, offset: int) -> None:
        """Update the last log read offset."""
        async with self._session_factory() as session:
            await session.execute(
                update(FactoryRun)
                .where(FactoryRun.id == run_id)
                .values(last_log_offset=offset)
            )

    async def answer_clarification(
        self,
        run_id: UUID,
        question_id: int,
        answer: str,
    ) -> None:
        """Write answer to clarification-answers.json in project directory."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(FactoryRun).where(FactoryRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if not run or not run.project_dir:
                raise ValueError(f"Run {run_id} not found")

        answers_file = Path(run.project_dir) / "artifacts" / "reports" / "clarification-answers.json"
        answers_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing answers
        existing = []
        if answers_file.exists():
            try:
                existing = json.loads(answers_file.read_text())
            except json.JSONDecodeError:
                existing = []

        # Add new answer
        existing.append({
            "question_id": question_id,
            "answer": answer,
            "answered_at": datetime.utcnow().isoformat(),
        })

        answers_file.write_text(json.dumps(existing, indent=2))
        logger.info("clarification_answered", run_id=str(run_id), question_id=question_id)

    async def list_tmux_sessions(self) -> list[str]:
        """List all active tmux session names."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux", "list-sessions", "-F", "#{session_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return stdout.decode().strip().split("\n")
        except FileNotFoundError:
            logger.warning("tmux_not_found")
        except Exception as e:
            logger.warning("tmux_list_failed", error=str(e))

        return []

    # ── Private helpers ──

    async def _create_project_dir(self, project_dir: Path) -> None:
        """Create the project directory structure."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._create_project_dir_sync, project_dir)

    def _create_project_dir_sync(self, project_dir: Path) -> None:
        """Synchronous project directory creation."""
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "artifacts" / "requirements").mkdir(parents=True, exist_ok=True)
        (project_dir / "artifacts" / "reports").mkdir(parents=True, exist_ok=True)
        (project_dir / "artifacts" / "architecture").mkdir(parents=True, exist_ok=True)
        (project_dir / "artifacts" / "code" / "backend").mkdir(parents=True, exist_ok=True)
        (project_dir / "artifacts" / "code" / "frontend").mkdir(parents=True, exist_ok=True)
        (project_dir / "artifacts" / "tests").mkdir(parents=True, exist_ok=True)
        (project_dir / "artifacts" / "reviews").mkdir(parents=True, exist_ok=True)
        (project_dir / "artifacts" / "docs").mkdir(parents=True, exist_ok=True)
        (project_dir / "artifacts" / "release").mkdir(parents=True, exist_ok=True)

    async def _copy_engine_config(self, engine: str, project_dir: Path) -> None:
        """Copy engine config template to project directory."""
        config_file = ENGINE_CONFIGS.get(engine)
        if not config_file:
            return

        source = self._templates_dir / "engine_configs" / config_file
        dest = project_dir / config_file

        if source.exists():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, shutil.copy2, str(source), str(dest))
            logger.debug("engine_config_copied", engine=engine, dest=str(dest))
        else:
            logger.warning("engine_config_not_found", source=str(source))

    async def _write_requirements(self, project: Project, project_dir: Path) -> None:
        """Write raw-input.md with the approved requirements."""
        raw_input_path = project_dir / "artifacts" / "requirements" / "raw-input.md"
        content = f"# {project.name}\n\n{project.requirements}"

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, raw_input_path.write_text, content)

    async def _start_tmux_session(
        self, session_name: str, project_dir: Path, engine: str
    ) -> None:
        """Create a tmux session and start the factory command."""
        command = ENGINE_COMMANDS.get(engine, f"echo 'Unknown engine: {engine}'")

        # Create tmux session
        proc = await asyncio.create_subprocess_exec(
            "tmux", "new-session", "-d", "-s", session_name,
            "-c", str(project_dir),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            error = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"Failed to create tmux session: {error}")

        # Send the factory command
        proc = await asyncio.create_subprocess_exec(
            "tmux", "send-keys", "-t", session_name, command, "Enter",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        logger.info(
            "tmux_session_started",
            session=session_name,
            command=command,
            project_dir=str(project_dir),
        )
