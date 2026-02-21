"""Detect system capabilities for installation."""

from __future__ import annotations

import asyncio
import platform
import shutil
import subprocess
from typing import Any


class SystemDetector:
    """
    Detects the current system capabilities needed for a successful installation.

    Uses shutil.which() for binary detection, platform for OS info, and
    subprocess for version checks (synchronous) and asyncio for async variants.
    """

    def detect_os(self) -> str:
        """
        Detect the operating system.

        Returns:
            One of: "ubuntu", "debian", "macos", "arch", "fedora", "unknown"
        """
        system = platform.system().lower()
        if system == "darwin":
            return "macos"
        if system == "linux":
            # Try to read /etc/os-release
            try:
                with open("/etc/os-release") as f:
                    content = f.read().lower()
                if "ubuntu" in content:
                    return "ubuntu"
                if "debian" in content:
                    return "debian"
                if "arch" in content:
                    return "arch"
                if "fedora" in content or "rhel" in content or "centos" in content:
                    return "fedora"
            except OSError:
                pass
            return "linux"
        return "unknown"

    def detect_python(self) -> str | None:
        """
        Detect the Python version string of the current interpreter.

        Returns:
            Version string like "3.11.9" or None if not detected.
        """
        try:
            result = subprocess.run(
                ["python3", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # "Python 3.11.9" -> "3.11.9"
                return result.stdout.strip().split()[-1]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        # Fall back to platform module
        version_info = platform.python_version()
        if version_info:
            return version_info
        return None

    def detect_docker(self) -> bool:
        """
        Return True if Docker is installed and accessible.
        """
        if shutil.which("docker") is None:
            return False
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def detect_postgres(self) -> bool:
        """
        Return True if PostgreSQL client tools are installed.
        """
        return shutil.which("psql") is not None or shutil.which("pg_isready") is not None

    def detect_engines(self) -> dict[str, bool]:
        """
        Detect which AI engine CLIs are installed.

        Returns:
            Dict mapping engine name to True/False availability.
        """
        engines = {
            "claude": shutil.which("claude") is not None,
            "gemini": shutil.which("gemini") is not None,
            "opencode": shutil.which("opencode") is not None,
            "aider": shutil.which("aider") is not None,
        }
        return engines

    def detect_node(self) -> str | None:
        """
        Detect Node.js version string.

        Returns:
            Version string like "20.11.1" or None if not installed.
        """
        if shutil.which("node") is None:
            return None
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip().lstrip("v")
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        return None

    def detect_npm(self) -> bool:
        """Return True if npm is available."""
        return shutil.which("npm") is not None

    def detect_go(self) -> str | None:
        """
        Detect Go version string.

        Returns:
            Version string like "1.22.0" or None if not installed.
        """
        if shutil.which("go") is None:
            return None
        try:
            result = subprocess.run(
                ["go", "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # "go version go1.22.0 linux/amd64" -> "1.22.0"
                parts = result.stdout.split()
                if len(parts) >= 3:
                    return parts[2].lstrip("go")
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        return None

    def detect_systemd(self) -> bool:
        """Return True if systemd is available (Linux only)."""
        return shutil.which("systemctl") is not None

    def full_report(self) -> dict[str, Any]:
        """
        Run all detections and return a consolidated report.

        Returns:
            Dict with keys: os, python, docker, postgres, node, npm, go,
            systemd, engines.
        """
        return {
            "os": self.detect_os(),
            "python": self.detect_python(),
            "docker": self.detect_docker(),
            "postgres": self.detect_postgres(),
            "node": self.detect_node(),
            "npm": self.detect_npm(),
            "go": self.detect_go(),
            "systemd": self.detect_systemd(),
            "engines": self.detect_engines(),
        }

    async def full_report_async(self) -> dict[str, Any]:
        """
        Run full_report in a thread pool to avoid blocking the event loop.
        """
        return await asyncio.to_thread(self.full_report)
