"""Project CRUD service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import delete, func, select, update

from app.models.project import Project

if TYPE_CHECKING:
    from app.database.session import AsyncSessionFactory

logger = structlog.get_logger()


class ProjectService:
    """CRUD operations for projects."""

    def __init__(self, session_factory: "AsyncSessionFactory") -> None:
        self._session_factory = session_factory

    async def create_project(
        self,
        name: str,
        description: str,
        engines: list[str],
        requirements: str,
        settings: dict,
        deploy_config: dict,
        created_by: int,
    ) -> Project:
        """Create a new project and return it."""
        async with self._session_factory() as session:
            project = Project(
                name=name,
                description=description,
                engines=engines,
                requirements=requirements,
                settings_json=settings,
                deploy_config=deploy_config,
                created_by=created_by,
                status="draft",
            )
            session.add(project)
            await session.flush()
            await session.refresh(project)

            logger.info(
                "project_created",
                project_id=str(project.id),
                name=name,
                engines=engines,
                created_by=created_by,
            )
            return project

    async def get_project(self, project_id: UUID) -> Project | None:
        """Get project by ID, or None if not found."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Project).where(Project.id == project_id)
            )
            return result.scalar_one_or_none()

    async def get_project_by_name(self, name: str) -> Project | None:
        """Get project by name, or None if not found."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Project).where(Project.name == name)
            )
            return result.scalar_one_or_none()

    async def list_projects(
        self,
        offset: int = 0,
        limit: int = 20,
        status_filter: str | None = None,
    ) -> tuple[list[Project], int]:
        """List projects with pagination. Returns (projects, total_count)."""
        async with self._session_factory() as session:
            query = select(Project)
            count_query = select(func.count()).select_from(Project)

            if status_filter:
                query = query.where(Project.status == status_filter)
                count_query = count_query.where(Project.status == status_filter)

            # Get total count
            count_result = await session.execute(count_query)
            total = count_result.scalar() or 0

            # Get projects
            query = query.order_by(Project.updated_at.desc()).offset(offset).limit(limit)
            result = await session.execute(query)
            projects = list(result.scalars().all())

            return projects, total

    async def delete_project(self, project_id: UUID) -> bool:
        """Delete project and all associated data. Returns success."""
        async with self._session_factory() as session:
            result = await session.execute(
                delete(Project).where(Project.id == project_id)
            )
            deleted = result.rowcount > 0

        if deleted:
            logger.info("project_deleted", project_id=str(project_id))

        return deleted

    async def update_status(self, project_id: UUID, status: str) -> None:
        """Update project status."""
        async with self._session_factory() as session:
            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(status=status)
            )
            logger.info(
                "project_status_updated",
                project_id=str(project_id),
                status=status,
            )

    async def update_cost(self, project_id: UUID, cost_delta: float) -> None:
        """Increment project total cost."""
        async with self._session_factory() as session:
            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(total_cost=Project.total_cost + cost_delta)
            )

    async def set_github_url(self, project_id: UUID, url: str) -> None:
        """Set the GitHub URL for a project."""
        async with self._session_factory() as session:
            await session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(github_url=url)
            )
