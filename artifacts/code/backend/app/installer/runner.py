"""Orchestrate installation steps."""

from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.installer.detector import SystemDetector

logger = structlog.get_logger()

# Ordered list of installation steps
INSTALL_STEPS = [
    "postgres",
    "python",
    "engines",
    "docker",
    "systemd",
]


class InstallerRunner:
    """
    Orchestrates the full installation sequence.

    Each step is a named async function that returns True on success.
    The runner records results and stops on critical failures.
    """

    def __init__(self, detector: "SystemDetector") -> None:
        self._detector = detector
        self._results: dict[str, bool] = {}

    async def run_full_install(self) -> dict[str, Any]:
        """
        Run all installation steps in order.

        Returns:
            Dict with keys:
                - steps: dict[str_name, bool] — per-step results
                - success: bool — True if all steps passed
                - report: dict — system detection report run before steps
                - errors: list[str] — any error messages collected
        """
        errors: list[str] = []
        report = await self._detector.full_report_async()

        logger.info("full_install_starting", system_report=report)

        for step_name in INSTALL_STEPS:
            logger.info("install_step_starting", step=step_name)
            try:
                ok = await self.run_step(step_name)
                self._results[step_name] = ok
                if ok:
                    logger.info("install_step_success", step=step_name)
                else:
                    logger.warning("install_step_failed", step=step_name)
                    errors.append(f"Step '{step_name}' failed.")
            except Exception as exc:
                logger.exception("install_step_error", step=step_name, error=str(exc))
                self._results[step_name] = False
                errors.append(f"Step '{step_name}' raised: {exc}")

        all_ok = all(self._results.values()) if self._results else False
        logger.info(
            "full_install_complete",
            success=all_ok,
            steps=self._results,
        )

        return {
            "steps": dict(self._results),
            "success": all_ok,
            "report": report,
            "errors": errors,
        }

    async def run_step(self, step_name: str) -> bool:
        """
        Run a single named installation step.

        Args:
            step_name: One of the keys in INSTALL_STEPS.

        Returns:
            True if the step succeeded, False otherwise.

        Raises:
            ValueError: If step_name is not recognised.
        """
        if step_name == "postgres":
            from app.installer.steps.postgres import check_postgres_running, install_postgres
            if await check_postgres_running():
                logger.info("postgres_already_running")
                return True
            return await install_postgres()

        if step_name == "python":
            from app.installer.steps.python import setup_venv, install_requirements
            import os
            project_dir = os.getcwd()
            venv_dir = os.path.join(project_dir, ".venv")
            req_file = os.path.join(project_dir, "requirements.txt")
            if not await setup_venv(project_dir):
                return False
            return await install_requirements(venv_dir, req_file)

        if step_name == "engines":
            from app.installer.steps.engines import install_all_engines
            results = await install_all_engines()
            # At least one engine must succeed
            success = any(results.values())
            logger.info("engines_installed", results=results)
            return success

        if step_name == "docker":
            from app.installer.steps.docker import install_docker
            report = await self._detector.full_report_async()
            if report.get("docker"):
                logger.info("docker_already_installed")
                return True
            return await install_docker()

        if step_name == "systemd":
            from app.installer.steps.systemd import install_services, enable_services
            import os
            import getpass
            user = getpass.getuser()
            working_dir = os.getcwd()
            if not await install_services(user=user, working_dir=working_dir):
                return False
            return await enable_services()

        raise ValueError(f"Unknown installation step: {step_name!r}")

    @property
    def results(self) -> dict[str, bool]:
        """Return the per-step results from the most recent run."""
        return dict(self._results)
