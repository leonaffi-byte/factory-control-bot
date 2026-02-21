"""Analytics service — cost tracking and metrics aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import func, select

from app.models.analytics import Analytics
from app.models.factory_run import FactoryRun
from app.models.project import Project

if TYPE_CHECKING:
    from app.database.session import AsyncSessionFactory

logger = structlog.get_logger()


class ProjectAnalytics(BaseModel):
    """Per-project analytics data."""
    project_id: UUID
    total_cost: float
    cost_by_provider: dict[str, float]
    cost_by_phase: dict[int, float]
    duration_minutes: float | None
    quality_scores: dict[int, float]
    test_passed: int = 0
    test_failed: int = 0
    test_skipped: int = 0


class AggregateAnalytics(BaseModel):
    """Aggregate analytics for a time period."""
    period: str
    total_spend: float
    projects_completed: int
    projects_failed: int
    avg_cost_by_tier: dict[int, float]
    success_rate: float
    projects_this_period: int


class EngineComparison(BaseModel):
    """Engine comparison for parallel runs."""
    engine: str
    total_cost: float
    duration_minutes: float
    quality_avg: float
    test_pass_rate: float


class AnalyticsService:
    """Analytics queries and cost recording."""

    def __init__(self, session_factory: "AsyncSessionFactory") -> None:
        self._session_factory = session_factory

    async def get_project_analytics(self, project_id: UUID) -> ProjectAnalytics:
        """Get per-project analytics."""
        async with self._session_factory() as session:
            # Get cost data
            cost_query = (
                select(
                    Analytics.provider,
                    Analytics.phase,
                    func.sum(Analytics.metric_value).label("total"),
                )
                .where(
                    Analytics.project_id == project_id,
                    Analytics.metric_name == "cost",
                )
                .group_by(Analytics.provider, Analytics.phase)
            )
            cost_result = await session.execute(cost_query)
            cost_rows = cost_result.all()

            cost_by_provider: dict[str, float] = {}
            cost_by_phase: dict[int, float] = {}
            total_cost = 0.0

            for row in cost_rows:
                provider = row.provider or "unknown"
                phase = row.phase or 0
                amount = float(row.total or 0)

                cost_by_provider[provider] = cost_by_provider.get(provider, 0) + amount
                cost_by_phase[phase] = cost_by_phase.get(phase, 0) + amount
                total_cost += amount

            # Get quality scores
            quality_query = (
                select(Analytics.phase, Analytics.metric_value)
                .where(
                    Analytics.project_id == project_id,
                    Analytics.metric_name == "quality_score",
                )
            )
            quality_result = await session.execute(quality_query)
            quality_scores = {
                int(row.phase): float(row.metric_value)
                for row in quality_result.all()
                if row.phase is not None
            }

            # Get test results
            test_metrics = {}
            for metric_name in ("test_passed", "test_failed", "test_skipped"):
                test_query = (
                    select(func.sum(Analytics.metric_value))
                    .where(
                        Analytics.project_id == project_id,
                        Analytics.metric_name == metric_name,
                    )
                )
                test_result = await session.execute(test_query)
                test_metrics[metric_name] = int(test_result.scalar() or 0)

            # Get duration
            duration_query = (
                select(func.sum(Analytics.metric_value))
                .where(
                    Analytics.project_id == project_id,
                    Analytics.metric_name == "duration_minutes",
                )
            )
            duration_result = await session.execute(duration_query)
            duration = duration_result.scalar()

            return ProjectAnalytics(
                project_id=project_id,
                total_cost=total_cost,
                cost_by_provider=cost_by_provider,
                cost_by_phase=cost_by_phase,
                duration_minutes=float(duration) if duration else None,
                quality_scores=quality_scores,
                test_passed=test_metrics.get("test_passed", 0),
                test_failed=test_metrics.get("test_failed", 0),
                test_skipped=test_metrics.get("test_skipped", 0),
            )

    async def get_aggregate_analytics(self, period: str = "month") -> AggregateAnalytics:
        """Get aggregate analytics for the given period."""
        now = datetime.utcnow()
        if period == "week":
            start_date = now - timedelta(weeks=1)
        elif period == "month":
            start_date = now - timedelta(days=30)
        elif period == "year":
            start_date = now - timedelta(days=365)
        else:
            start_date = now - timedelta(days=30)

        async with self._session_factory() as session:
            # Total spend
            spend_query = (
                select(func.sum(Analytics.metric_value))
                .where(
                    Analytics.metric_name == "cost",
                    Analytics.created_at >= start_date,
                )
            )
            spend_result = await session.execute(spend_query)
            total_spend = float(spend_result.scalar() or 0)

            # Projects counts
            completed_query = (
                select(func.count())
                .select_from(Project)
                .where(
                    Project.status == "completed",
                    Project.updated_at >= start_date,
                )
            )
            completed_result = await session.execute(completed_query)
            projects_completed = completed_result.scalar() or 0

            failed_query = (
                select(func.count())
                .select_from(Project)
                .where(
                    Project.status == "failed",
                    Project.updated_at >= start_date,
                )
            )
            failed_result = await session.execute(failed_query)
            projects_failed = failed_result.scalar() or 0

            total_projects_query = (
                select(func.count())
                .select_from(Project)
                .where(Project.created_at >= start_date)
            )
            total_projects_result = await session.execute(total_projects_query)
            projects_this_period = total_projects_result.scalar() or 0

            # Success rate
            total_finished = projects_completed + projects_failed
            success_rate = (
                projects_completed / total_finished if total_finished > 0 else 0.0
            )

            # Average cost by tier (approximated from settings_json)
            # For now return empty — would require parsing settings_json
            avg_cost_by_tier: dict[int, float] = {}

            return AggregateAnalytics(
                period=period,
                total_spend=total_spend,
                projects_completed=projects_completed,
                projects_failed=projects_failed,
                avg_cost_by_tier=avg_cost_by_tier,
                success_rate=success_rate,
                projects_this_period=projects_this_period,
            )

    async def get_engine_comparison(
        self, project_id: UUID
    ) -> list[EngineComparison] | None:
        """Compare engines for a project with parallel runs."""
        async with self._session_factory() as session:
            runs_query = (
                select(FactoryRun)
                .where(
                    FactoryRun.project_id == project_id,
                    FactoryRun.status == "completed",
                )
            )
            runs_result = await session.execute(runs_query)
            runs = runs_result.scalars().all()

            if len(runs) < 2:
                return None

            comparisons = []
            for run in runs:
                # Get quality scores
                quality_query = (
                    select(func.avg(Analytics.metric_value))
                    .where(
                        Analytics.run_id == run.id,
                        Analytics.metric_name == "quality_score",
                    )
                )
                quality_result = await session.execute(quality_query)
                quality_avg = float(quality_result.scalar() or 0)

                # Get test pass rate
                passed_query = (
                    select(func.sum(Analytics.metric_value))
                    .where(
                        Analytics.run_id == run.id,
                        Analytics.metric_name == "test_passed",
                    )
                )
                passed_result = await session.execute(passed_query)
                passed = float(passed_result.scalar() or 0)

                total_tests_query = (
                    select(func.sum(Analytics.metric_value))
                    .where(
                        Analytics.run_id == run.id,
                        Analytics.metric_name.in_(["test_passed", "test_failed"]),
                    )
                )
                total_tests_result = await session.execute(total_tests_query)
                total_tests = float(total_tests_result.scalar() or 0)

                test_pass_rate = passed / total_tests if total_tests > 0 else 0.0

                comparisons.append(EngineComparison(
                    engine=run.engine,
                    total_cost=float(run.total_cost or 0),
                    duration_minutes=float(run.duration_minutes or 0),
                    quality_avg=quality_avg,
                    test_pass_rate=test_pass_rate,
                ))

            return comparisons

    async def record_cost_entry(
        self,
        run_id: UUID,
        project_id: UUID,
        amount: float,
        provider: str,
        engine: str | None = None,
        phase: int | None = None,
    ) -> None:
        """Record a cost entry."""
        async with self._session_factory() as session:
            entry = Analytics(
                project_id=project_id,
                run_id=run_id,
                metric_name="cost",
                metric_value=amount,
                provider=provider,
                engine=engine,
                phase=phase,
            )
            session.add(entry)

    async def record_metric(
        self,
        project_id: UUID,
        run_id: UUID | None,
        metric_name: str,
        metric_value: float,
        provider: str | None = None,
        engine: str | None = None,
        phase: int | None = None,
    ) -> None:
        """Record a generic analytics metric."""
        async with self._session_factory() as session:
            entry = Analytics(
                project_id=project_id,
                run_id=run_id,
                metric_name=metric_name,
                metric_value=metric_value,
                provider=provider,
                engine=engine,
                phase=phase,
            )
            session.add(entry)
