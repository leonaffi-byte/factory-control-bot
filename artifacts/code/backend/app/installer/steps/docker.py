"""Docker installation step."""

from __future__ import annotations

import asyncio
import os
import shutil

import structlog

logger = structlog.get_logger()


async def install_docker() -> bool:
    """
    Install Docker Engine using the official convenience script on Linux,
    or provide instructions for macOS.

    Returns:
        True if Docker was installed and is running.
    """
    system = _detect_system()

    if system == "macos":
        logger.info(
            "docker_install_macos_hint",
            message="Docker Desktop must be installed manually on macOS. "
                    "Download from https://www.docker.com/products/docker-desktop",
        )
        return shutil.which("docker") is not None

    if system not in ("linux", "ubuntu", "debian"):
        logger.warning("docker_unsupported_platform", system=system)
        return False

    # Use Docker's official install script
    logger.info("installing_docker_via_convenience_script")
    try:
        # Download script
        proc = await asyncio.create_subprocess_exec(
            "sh", "-c",
            "curl -fsSL https://get.docker.com | sh",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(
                "docker_install_script_failed",
                returncode=proc.returncode,
                stderr=stderr.decode(errors="replace")[:800],
            )
            return False
    except OSError as e:
        logger.error("docker_install_error", error=str(e))
        return False

    # Add current user to docker group
    user = os.environ.get("USER", "")
    if user:
        try:
            proc = await asyncio.create_subprocess_exec(
                "usermod", "-aG", "docker", user,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            logger.info("user_added_to_docker_group", user=user)
        except OSError:
            pass

    # Enable and start docker service
    for cmd in (
        ["systemctl", "enable", "docker"],
        ["systemctl", "start", "docker"],
    ):
        if shutil.which(cmd[0]):
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            except OSError:
                pass

    logger.info("docker_installed")
    return True


async def setup_compose(project_dir: str) -> bool:
    """
    Verify docker-compose (or docker compose plugin) is available
    and run `docker compose up -d` in the project directory.

    Args:
        project_dir: Absolute path to the directory containing docker-compose.yml.

    Returns:
        True if `docker compose up -d` exited with code 0.
    """
    compose_file = os.path.join(project_dir, "docker-compose.yml")
    if not os.path.isfile(compose_file):
        compose_file = os.path.join(project_dir, "docker-compose.yaml")
        if not os.path.isfile(compose_file):
            logger.error("docker_compose_file_not_found", project_dir=project_dir)
            return False

    # Prefer `docker compose` (plugin) over standalone `docker-compose`
    if shutil.which("docker"):
        compose_cmd = ["docker", "compose", "up", "-d", "--remove-orphans"]
    elif shutil.which("docker-compose"):
        compose_cmd = ["docker-compose", "up", "-d", "--remove-orphans"]
    else:
        logger.error("docker_compose_not_found")
        return False

    logger.info("running_docker_compose", project_dir=project_dir)
    try:
        proc = await asyncio.create_subprocess_exec(
            *compose_cmd,
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("docker_compose_started", project_dir=project_dir)
            return True
        logger.error(
            "docker_compose_failed",
            returncode=proc.returncode,
            stderr=stderr.decode(errors="replace")[:800],
        )
        return False
    except OSError as e:
        logger.error("docker_compose_error", error=str(e))
        return False


def _detect_system() -> str:
    """Quick OS detection for use within this module."""
    import platform
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "linux":
        try:
            with open("/etc/os-release") as f:
                content = f.read().lower()
            if "ubuntu" in content:
                return "ubuntu"
            if "debian" in content:
                return "debian"
        except OSError:
            pass
        return "linux"
    return "unknown"
