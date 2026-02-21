"""Cost tracker service — per-provider API usage and budget monitoring."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import func, select

from app.models.api_usage import ApiUsageLog

if TYPE_CHECKING:
    from app.database.session import AsyncSessionFactory

logger = structlog.get_logger()


class CostTracker:
    """
    Records API usage events and provides cost aggregation queries.

    All monetary values are in USD.
    """

    def __init__(self, session_factory: "AsyncSessionFactory") -> None:
        self._session_factory = session_factory

    async def record_usage(
        self,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost: float,
        run_id: UUID | None = None,
        role: str = "unknown",
        phase: int | None = None,
        success: bool = True,
        latency_ms: int = 0,
        error_type: str | None = None,
    ) -> None:
        """
        Persist a single API call record to the usage log.

        Args:
            provider: Provider name (e.g. "groq", "openrouter").
            model: Model identifier.
            tokens_in: Input token count.
            tokens_out: Output token count.
            cost: Estimated cost in USD (0.0 for free providers).
            run_id: Optional associated factory run UUID.
            role: Agent role that made the call.
            phase: Pipeline phase number (0-7).
            success: Whether the call succeeded.
            latency_ms: Round-trip latency in milliseconds.
            error_type: Short error class name if the call failed.
        """
        async with self._session_factory() as session:
            entry = ApiUsageLog(
                provider_name=provider,
                model_name=model,
                role=role,
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                cost_estimated=cost,
                is_free=(cost == 0.0),
                latency_ms=latency_ms,
                success=success,
                error_type=error_type,
                factory_run_id=run_id,
                phase=phase,
            )
            session.add(entry)

        logger.debug(
            "usage_recorded",
            provider=provider,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
            run_id=str(run_id) if run_id else None,
        )

    async def get_daily_cost(
        self, provider: str | None = None
    ) -> float:
        """
        Return the total estimated cost for today's API calls.

        Args:
            provider: Filter to a specific provider, or None for all providers.

        Returns:
            Summed cost in USD as a float (0.0 if no records).
        """
        today = date.today()
        async with self._session_factory() as session:
            query = select(func.sum(ApiUsageLog.cost_estimated)).where(
                func.date(ApiUsageLog.created_at) == today
            )
            if provider is not None:
                query = query.where(ApiUsageLog.provider_name == provider)

            result = await session.execute(query)
            total = result.scalar()

        return float(total or 0.0)

    async def get_run_cost(self, run_id: UUID) -> float:
        """
        Return the total estimated cost for all API calls in a factory run.

        Args:
            run_id: UUID of the FactoryRun.

        Returns:
            Summed cost in USD as a float.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.sum(ApiUsageLog.cost_estimated)).where(
                    ApiUsageLog.factory_run_id == run_id
                )
            )
            total = result.scalar()

        return float(total or 0.0)

    async def get_run_cost_by_provider(
        self, run_id: UUID
    ) -> dict[str, float]:
        """
        Return per-provider cost breakdown for a single factory run.

        Returns:
            Dict mapping provider_name -> total cost USD.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(
                    ApiUsageLog.provider_name,
                    func.sum(ApiUsageLog.cost_estimated),
                )
                .where(ApiUsageLog.factory_run_id == run_id)
                .group_by(ApiUsageLog.provider_name)
            )
            rows = result.all()

        return {row[0]: float(row[1] or 0.0) for row in rows}

    async def check_budget(self, threshold: float) -> bool:
        """
        Check whether today's spending has exceeded the given threshold.

        Args:
            threshold: Budget limit in USD.

        Returns:
            True if today's cost is WITHIN budget (i.e. under threshold),
            False if the threshold has been exceeded.
        """
        daily_cost = await self.get_daily_cost()
        within_budget = daily_cost < threshold

        if not within_budget:
            logger.warning(
                "budget_threshold_exceeded",
                daily_cost=daily_cost,
                threshold=threshold,
            )

        return within_budget

    async def get_total_tokens(
        self,
        provider: str | None = None,
        since: datetime | None = None,
    ) -> dict[str, int]:
        """
        Return total token counts (input + output) across all calls.

        Args:
            provider: Filter to a specific provider, or None for all.
            since: Only include calls after this datetime (UTC).

        Returns:
            Dict with keys "tokens_input" and "tokens_output".
        """
        async with self._session_factory() as session:
            query = select(
                func.sum(ApiUsageLog.tokens_input),
                func.sum(ApiUsageLog.tokens_output),
            )
            if provider:
                query = query.where(ApiUsageLog.provider_name == provider)
            if since:
                query = query.where(ApiUsageLog.created_at >= since)

            result = await session.execute(query)
            row = result.one()

        return {
            "tokens_input": int(row[0] or 0),
            "tokens_output": int(row[1] or 0),
        }
