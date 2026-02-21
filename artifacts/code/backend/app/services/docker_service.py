"""Docker container management service via aiodocker."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class ContainerInfo(BaseModel):
    """Docker container information."""
    id: str
    name: str
    image: str
    status: str
    state: str
    ports: dict[str, str | None] = {}
    created: datetime
    cpu_percent: float | None = None
    memory_mb: float | None = None


class DockerError(Exception):
    """Docker operation failed."""
    pass


class DockerService:
    """Manages Docker containers via aiodocker."""

    def __init__(self) -> None:
        self._docker = None

    async def _get_client(self):
        """Lazy-initialize aiodocker client."""
        if self._docker is None:
            import aiodocker
            self._docker = aiodocker.Docker()
        return self._docker

    async def close(self) -> None:
        """Close the Docker client."""
        if self._docker is not None:
            await self._docker.close()
            self._docker = None

    async def list_containers(self, all: bool = True) -> list[ContainerInfo]:
        """List all Docker containers with stats."""
        docker = await self._get_client()

        try:
            containers = await docker.containers.list(all=all)
        except Exception as e:
            raise DockerError(f"Failed to list containers: {e}") from e

        result = []
        for container in containers:
            info = await self._container_to_info(container)
            result.append(info)

        return result

    async def start_container(self, container_id: str) -> None:
        """Start a stopped container."""
        docker = await self._get_client()
        try:
            container = await docker.containers.get(container_id)
            await container.start()
            logger.info("container_started", container_id=container_id)
        except Exception as e:
            raise DockerError(f"Failed to start container: {e}") from e

    async def stop_container(self, container_id: str) -> None:
        """Stop a running container."""
        docker = await self._get_client()
        try:
            container = await docker.containers.get(container_id)
            await container.stop()
            logger.info("container_stopped", container_id=container_id)
        except Exception as e:
            raise DockerError(f"Failed to stop container: {e}") from e

    async def restart_container(self, container_id: str) -> None:
        """Restart a container."""
        docker = await self._get_client()
        try:
            container = await docker.containers.get(container_id)
            await container.restart()
            logger.info("container_restarted", container_id=container_id)
        except Exception as e:
            raise DockerError(f"Failed to restart container: {e}") from e

    async def get_logs(self, container_id: str, tail: int = 50) -> str:
        """Get last N lines of container logs."""
        docker = await self._get_client()
        try:
            container = await docker.containers.get(container_id)
            logs = await container.log(stdout=True, stderr=True, tail=tail)
            return "\n".join(logs) if isinstance(logs, list) else str(logs)
        except Exception as e:
            raise DockerError(f"Failed to get logs: {e}") from e

    async def remove_container(self, container_id: str, force: bool = False) -> None:
        """Remove a container."""
        docker = await self._get_client()
        try:
            container = await docker.containers.get(container_id)
            await container.delete(force=force)
            logger.info("container_removed", container_id=container_id, force=force)
        except Exception as e:
            raise DockerError(f"Failed to remove container: {e}") from e

    async def compose_up(self, project_dir: str) -> None:
        """Run docker-compose up -d in the given directory."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "up", "-d",
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            error = stderr.decode() if stderr else "Unknown error"
            raise DockerError(f"docker-compose up failed: {error}")
        logger.info("compose_up", project_dir=project_dir)

    async def compose_down(self, project_dir: str) -> None:
        """Run docker-compose down in the given directory."""
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "down",
            cwd=project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            error = stderr.decode() if stderr else "Unknown error"
            raise DockerError(f"docker-compose down failed: {error}")
        logger.info("compose_down", project_dir=project_dir)

    async def _container_to_info(self, container) -> ContainerInfo:
        """Convert an aiodocker container to ContainerInfo."""
        info = container._container  # Raw container info dict

        # Parse ports
        ports = {}
        port_bindings = info.get("Ports", [])
        if isinstance(port_bindings, list):
            for port_info in port_bindings:
                private = f"{port_info.get('PrivatePort', '')}/{port_info.get('Type', 'tcp')}"
                public = str(port_info.get("PublicPort", "")) if port_info.get("PublicPort") else None
                ports[private] = public

        # Parse name
        names = info.get("Names", ["/unknown"])
        name = names[0] if names else "/unknown"

        # Parse timestamps
        created_ts = info.get("Created", 0)
        created = datetime.fromtimestamp(created_ts) if isinstance(created_ts, (int, float)) else datetime.utcnow()

        # Get stats (CPU/memory) — optional, may fail
        cpu_percent = None
        memory_mb = None
        try:
            stats = await container.stats(stream=False)
            if stats:
                stat = stats[0] if isinstance(stats, list) else stats
                cpu_percent = self._calc_cpu_percent(stat)
                memory_mb = self._calc_memory_mb(stat)
        except Exception:
            pass  # Stats not always available

        return ContainerInfo(
            id=info.get("Id", ""),
            name=name,
            image=info.get("Image", ""),
            status=info.get("Status", ""),
            state=info.get("State", "unknown"),
            ports=ports,
            created=created,
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
        )

    @staticmethod
    def _calc_cpu_percent(stats: dict) -> float | None:
        """Calculate CPU percentage from stats."""
        try:
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})

            cpu_delta = (
                cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
                - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            )
            system_delta = (
                cpu_stats.get("system_cpu_usage", 0)
                - precpu_stats.get("system_cpu_usage", 0)
            )

            if system_delta > 0 and cpu_delta >= 0:
                num_cpus = len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", [1]))
                return (cpu_delta / system_delta) * num_cpus * 100.0

        except (KeyError, TypeError, ZeroDivisionError):
            pass
        return None

    @staticmethod
    def _calc_memory_mb(stats: dict) -> float | None:
        """Calculate memory usage in MB from stats."""
        try:
            mem_stats = stats.get("memory_stats", {})
            usage = mem_stats.get("usage", 0)
            cache = mem_stats.get("stats", {}).get("cache", 0)
            return (usage - cache) / (1024 * 1024)
        except (KeyError, TypeError):
            pass
        return None
