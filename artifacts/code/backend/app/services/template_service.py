"""Template service — project template management and application."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.config import Settings

logger = structlog.get_logger()

# Built-in template definitions (used when no YAML/JSON templates are found on disk)
_BUILTIN_TEMPLATES: dict[str, dict] = {
    "blank": {
        "name": "blank",
        "description": "Empty project with the standard directory structure.",
        "directories": [
            "artifacts/requirements",
            "artifacts/architecture",
            "artifacts/code/backend",
            "artifacts/code/frontend",
            "artifacts/tests",
            "artifacts/reviews",
            "artifacts/docs",
            "artifacts/release",
            "artifacts/reports",
        ],
        "files": {},
    },
    "telegram-bot": {
        "name": "telegram-bot",
        "description": "Telegram bot starter with aiogram 3.x skeleton.",
        "directories": [
            "artifacts/requirements",
            "artifacts/architecture",
            "artifacts/code/backend",
            "artifacts/code/frontend",
            "artifacts/tests",
            "artifacts/reviews",
            "artifacts/docs",
            "artifacts/release",
            "artifacts/reports",
        ],
        "files": {
            "artifacts/requirements/raw-input.md": (
                "# Telegram Bot Project\n\n"
                "Build a Telegram bot using aiogram 3.x.\n"
            ),
        },
    },
    "rest-api": {
        "name": "rest-api",
        "description": "FastAPI REST API with PostgreSQL and SQLAlchemy.",
        "directories": [
            "artifacts/requirements",
            "artifacts/architecture",
            "artifacts/code/backend",
            "artifacts/tests",
            "artifacts/reviews",
            "artifacts/docs",
            "artifacts/release",
            "artifacts/reports",
        ],
        "files": {
            "artifacts/requirements/raw-input.md": (
                "# REST API Project\n\n"
                "Build a REST API with FastAPI and PostgreSQL.\n"
            ),
        },
    },
    "full-stack": {
        "name": "full-stack",
        "description": "Full-stack web app: FastAPI backend + React/Next.js frontend.",
        "directories": [
            "artifacts/requirements",
            "artifacts/architecture",
            "artifacts/code/backend",
            "artifacts/code/frontend",
            "artifacts/tests",
            "artifacts/reviews",
            "artifacts/docs",
            "artifacts/release",
            "artifacts/reports",
        ],
        "files": {
            "artifacts/requirements/raw-input.md": (
                "# Full Stack Web App\n\n"
                "Build a full-stack app with FastAPI and React.\n"
            ),
        },
    },
}


class TemplateNotFoundError(ValueError):
    """Raised when a requested template does not exist."""


class TemplateService:
    """
    Manages project templates — lists available templates, loads their definitions,
    and applies them to a target project directory.

    Templates are looked up first from disk (settings.templates_dir/project_templates/)
    then from built-in defaults.
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._templates_dir = settings.templates_dir / "project_templates"

    def list_templates(self) -> list[str]:
        """
        Return the names of all available templates.

        Merges disk-based JSON templates with built-ins; disk templates take
        precedence when names collide.
        """
        names: set[str] = set(_BUILTIN_TEMPLATES.keys())

        if self._templates_dir.exists():
            for path in self._templates_dir.glob("*.json"):
                names.add(path.stem)

        return sorted(names)

    def get_template(self, name: str) -> dict:
        """
        Return the template definition dict for *name*.

        Searches disk first, then built-ins.

        Args:
            name: Template name (e.g. "telegram-bot", "rest-api").

        Returns:
            Template definition dict with keys: name, description, directories, files.

        Raises:
            TemplateNotFoundError: If the template does not exist.
        """
        # Check disk
        disk_path = self._templates_dir / f"{name}.json"
        if disk_path.exists():
            try:
                data = json.loads(disk_path.read_text(encoding="utf-8"))
                logger.debug("template_loaded_from_disk", name=name, path=str(disk_path))
                return data
            except json.JSONDecodeError as exc:
                logger.warning(
                    "template_json_parse_failed",
                    name=name,
                    path=str(disk_path),
                    error=str(exc),
                )

        # Fall back to built-ins
        if name in _BUILTIN_TEMPLATES:
            logger.debug("template_loaded_builtin", name=name)
            return dict(_BUILTIN_TEMPLATES[name])

        raise TemplateNotFoundError(
            f"Template '{name}' not found. Available: {self.list_templates()}"
        )

    async def apply_template(
        self, project_dir: Path, template: str
    ) -> None:
        """
        Apply *template* to *project_dir* by creating directories and writing files.

        Existing files are NOT overwritten (templates are additive).
        If the template name is a filesystem path and points to a directory,
        the entire directory is copied into project_dir instead.

        Args:
            project_dir: Absolute path to the target project directory.
            template: Template name (e.g. "telegram-bot") or a filesystem path.
        """
        # Handle filesystem path templates (e.g. /some/custom/template-dir)
        template_path = Path(template)
        if template_path.is_dir():
            await asyncio.to_thread(
                self._copy_directory_template, template_path, project_dir
            )
            logger.info(
                "template_applied_from_path",
                template=template,
                project_dir=str(project_dir),
            )
            return

        definition = self.get_template(template)

        await asyncio.to_thread(
            self._apply_definition, definition, project_dir
        )

        logger.info(
            "template_applied",
            template=template,
            project_dir=str(project_dir),
            directories=len(definition.get("directories", [])),
            files=len(definition.get("files", {})),
        )

    # ── Private helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _apply_definition(definition: dict, project_dir: Path) -> None:
        """Synchronous helper: create directories and write template files."""
        for rel_dir in definition.get("directories", []):
            target = project_dir / rel_dir
            target.mkdir(parents=True, exist_ok=True)

        for rel_path, content in definition.get("files", {}).items():
            target = project_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_text(content, encoding="utf-8")

    @staticmethod
    def _copy_directory_template(src: Path, project_dir: Path) -> None:
        """Synchronous helper: copy a directory template (skips existing files)."""
        for src_file in src.rglob("*"):
            if not src_file.is_file():
                continue
            relative = src_file.relative_to(src)
            dest_file = project_dir / relative
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            if not dest_file.exists():
                shutil.copy2(str(src_file), str(dest_file))
