"""Factory installer module."""

from __future__ import annotations

from app.installer.detector import SystemDetector
from app.installer.runner import InstallerRunner

__all__ = ["SystemDetector", "InstallerRunner"]
