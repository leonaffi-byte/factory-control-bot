"""Python environment setup step."""

from __future__ import annotations

import asyncio
import os

import structlog

logger = structlog.get_logger()


async def setup_venv(project_dir: str) -> bool:
    """
    Create a Python virtual environment at <project_dir>/.venv.

    Uses python3 -m venv.

    Args:
        project_dir: Absolute path to the project root directory.

    Returns:
        True if the venv was created or already exists.
    """
    venv_dir = os.path.join(project_dir, ".venv")

    # Check if already exists
    venv_python = os.path.join(venv_dir, "bin", "python")
    if os.path.isfile(venv_python):
        logger.info("venv_already_exists", venv_dir=venv_dir)
        return True

    logger.info("creating_venv", venv_dir=venv_dir)
    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", "-m", "venv", venv_dir,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("venv_created", venv_dir=venv_dir)
            return True
        logger.error(
            "venv_creation_failed",
            returncode=proc.returncode,
            stderr=stderr.decode(errors="replace")[:500],
        )
        return False
    except OSError as e:
        logger.error("venv_creation_error", error=str(e))
        return False


async def install_requirements(venv_dir: str, req_file: str) -> bool:
    """
    Install Python dependencies into the given venv from a requirements file.

    Args:
        venv_dir: Path to the virtual environment directory.
        req_file: Path to the requirements.txt file.

    Returns:
        True if pip install succeeded or requirements file does not exist.
    """
    pip_bin = os.path.join(venv_dir, "bin", "pip")

    if not os.path.isfile(req_file):
        logger.warning("requirements_file_not_found", req_file=req_file)
        return True  # Nothing to install — not a failure

    if not os.path.isfile(pip_bin):
        logger.error("pip_not_found_in_venv", pip_bin=pip_bin)
        return False

    logger.info("installing_requirements", req_file=req_file, venv_dir=venv_dir)
    try:
        proc = await asyncio.create_subprocess_exec(
            pip_bin, "install", "--upgrade", "pip",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        proc = await asyncio.create_subprocess_exec(
            pip_bin, "install", "-r", req_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("requirements_installed", req_file=req_file)
            return True
        logger.error(
            "requirements_install_failed",
            returncode=proc.returncode,
            stderr=stderr.decode(errors="replace")[:800],
        )
        return False
    except OSError as e:
        logger.error("requirements_install_error", error=str(e))
        return False
