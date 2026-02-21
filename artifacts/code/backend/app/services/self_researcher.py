"""Self-researcher service — autonomous factory self-improvement analysis."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import desc, select, update

from app.models.self_research import SelfResearchReport, SelfResearchSuggestion

if TYPE_CHECKING:
    from app.database.session import AsyncSessionFactory
    from app.services.model_router import ModelRouter

logger = structlog.get_logger()

# ── DTOs ────────────────────────────────────────────────────────────────────


@dataclass
class FileChange:
    file_path: str
    change_type: str   # "create" | "modify" | "delete"
    description: str


@dataclass
class ResearchSuggestion:
    category: str          # "performance" | "quality" | "cost" | "reliability" | "dx"
    title: str
    description: str
    risk_level: str        # "low" | "medium" | "high"
    expected_impact: str
    source_url: str | None = None


@dataclass
class ApplyResult:
    success: bool
    branch_name: str | None = None
    pr_url: str | None = None
    error: str | None = None


# ── Prompt templates ────────────────────────────────────────────────────────

_RESEARCH_SYSTEM_PROMPT = """\
You are an expert software architect analysing the factory-control-bot codebase for
improvement opportunities. Your task is to identify concrete, actionable suggestions
that would improve performance, reliability, cost-efficiency, code quality, or
developer experience.

For EACH suggestion output a JSON object with these keys:
  category       (string): one of: performance, quality, cost, reliability, dx
  title          (string): short title (max 80 chars)
  description    (string): detailed description of the change (2-5 sentences)
  risk_level     (string): low | medium | high
  expected_impact (string): specific, measurable expected outcome

Return a JSON array of such objects. No other text.
"""


class SelfResearcher:
    """
    Runs autonomous self-research on the factory codebase and applies suggestions.

    Workflow:
    1. Read codebase structure and key files.
    2. Send to the model router for analysis.
    3. Persist suggestions to the database.
    4. Optionally apply a suggestion by creating a git branch.
    """

    def __init__(
        self,
        session_factory: "AsyncSessionFactory",
        model_router: "ModelRouter",
    ) -> None:
        self._session_factory = session_factory
        self._model_router = model_router
        self._factory_root = Path(__file__).resolve().parents[3]

    async def run_research(
        self, triggered_by: str = "manual"
    ) -> SelfResearchReport:
        """
        Execute a full self-research cycle.

        1. Snapshot the codebase context.
        2. Query the model router for improvement ideas.
        3. Parse and persist suggestions.
        4. Return the persisted SelfResearchReport.

        Args:
            triggered_by: "manual" | "scheduled" | "admin"

        Returns:
            Persisted SelfResearchReport ORM instance.
        """
        started_at = datetime.now(timezone.utc)
        logger.info("self_research_started", triggered_by=triggered_by)

        context = await asyncio.to_thread(self._build_codebase_context)

        # Create initial report record
        async with self._session_factory() as session:
            report = SelfResearchReport(
                triggered_by=triggered_by,
                started_at=started_at,
            )
            session.add(report)
            await session.flush()
            await session.refresh(report)
            report_id: int = report.id

        suggestions: list[ResearchSuggestion] = []
        try:
            suggestions = await self._query_model(context)
        except Exception as exc:
            logger.error("self_research_model_failed", error=str(exc))

        # Persist suggestions
        async with self._session_factory() as session:
            for sug in suggestions:
                db_sug = SelfResearchSuggestion(
                    report_id=report_id,
                    category=sug.category,
                    title=sug.title,
                    description=sug.description,
                    risk_level=sug.risk_level,
                    expected_impact=sug.expected_impact,
                    status="pending",
                    changes_json={"source_url": sug.source_url},
                )
                session.add(db_sug)

            completed_at = datetime.now(timezone.utc)
            await session.execute(
                update(SelfResearchReport)
                .where(SelfResearchReport.id == report_id)
                .values(
                    suggestions_count=len(suggestions),
                    completed_at=completed_at,
                )
            )

        logger.info(
            "self_research_complete",
            report_id=report_id,
            suggestions=len(suggestions),
        )

        return await self._get_report_by_id(report_id)  # type: ignore[return-value]

    async def apply_suggestion(self, suggestion_id: int) -> ApplyResult:
        """
        Apply a pending suggestion by creating a git branch and committing stubs.

        Creates branch: self-research/<suggestion_id>
        Marks the suggestion status as "applied" on success or "failed" on error.

        Args:
            suggestion_id: Primary key of the SelfResearchSuggestion to apply.

        Returns:
            ApplyResult with success flag and branch name.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(SelfResearchSuggestion).where(
                    SelfResearchSuggestion.id == suggestion_id
                )
            )
            sug: SelfResearchSuggestion | None = result.scalar_one_or_none()

        if sug is None:
            return ApplyResult(
                success=False,
                error=f"Suggestion {suggestion_id} not found.",
            )

        branch_name = f"self-research/{suggestion_id}"

        try:
            await asyncio.to_thread(
                self._create_git_branch, branch_name, sug
            )
        except Exception as exc:
            logger.error(
                "suggestion_apply_failed",
                suggestion_id=suggestion_id,
                error=str(exc),
            )
            async with self._session_factory() as session:
                await session.execute(
                    update(SelfResearchSuggestion)
                    .where(SelfResearchSuggestion.id == suggestion_id)
                    .values(status="failed")
                )
            return ApplyResult(success=False, error=str(exc))

        async with self._session_factory() as session:
            await session.execute(
                update(SelfResearchSuggestion)
                .where(SelfResearchSuggestion.id == suggestion_id)
                .values(status="applied")
            )

        logger.info(
            "suggestion_applied",
            suggestion_id=suggestion_id,
            branch=branch_name,
        )
        return ApplyResult(success=True, branch_name=branch_name)

    async def get_latest_report(self) -> SelfResearchReport | None:
        """
        Return the most recent SelfResearchReport, or None if none exist.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(SelfResearchReport)
                .order_by(desc(SelfResearchReport.created_at))
                .limit(1)
            )
            return result.scalar_one_or_none()

    # ── Private helpers ─────────────────────────────────────────────────────

    def _build_codebase_context(self) -> str:
        """
        Build a compact summary of the codebase structure and key file contents
        to include in the research prompt.
        """
        lines: list[str] = ["# Factory Codebase Self-Research Context\n"]

        # Directory listing (two levels deep)
        try:
            result = subprocess.run(
                ["find", str(self._factory_root / "app"), "-name", "*.py",
                 "-not", "-path", "*/__pycache__/*"],
                capture_output=True, text=True, timeout=10
            )
            lines.append("## Python Files\n```\n")
            lines.append(result.stdout[:3000])
            lines.append("\n```\n")
        except Exception:
            pass

        # Snapshot a few key files for context
        key_files = [
            self._factory_root / "app" / "config.py",
            self._factory_root / "app" / "services" / "__init__.py",
            self._factory_root / "app" / "orchestrator" / "state_machine.py",
        ]
        for path in key_files:
            if path.exists():
                content = path.read_text(errors="replace")[:1500]
                lines.append(f"\n## {path.name}\n```python\n{content}\n```\n")

        return "".join(lines)

    async def _query_model(
        self, context: str
    ) -> list[ResearchSuggestion]:
        """Send context to the model router and parse the JSON response."""
        import json

        messages = [
            {"role": "system", "content": _RESEARCH_SYSTEM_PROMPT},
            {"role": "user", "content": context[:6000]},  # stay within context limit
        ]

        response = await self._model_router.route(
            role="reviewer",
            messages=messages,
            free_only=True,
            temperature=0.3,
            max_tokens=2048,
        )

        raw = response.content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
            if raw.endswith("```"):
                raw = raw[:-3].strip()

        try:
            items: list[dict] = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("self_research_json_parse_failed", error=str(exc))
            return []

        suggestions: list[ResearchSuggestion] = []
        for item in items:
            try:
                suggestions.append(
                    ResearchSuggestion(
                        category=str(item.get("category", "quality")),
                        title=str(item.get("title", ""))[:200],
                        description=str(item.get("description", "")),
                        risk_level=str(item.get("risk_level", "medium")),
                        expected_impact=str(item.get("expected_impact", "")),
                        source_url=item.get("source_url"),
                    )
                )
            except Exception:
                continue

        return suggestions

    def _create_git_branch(
        self, branch_name: str, suggestion: SelfResearchSuggestion
    ) -> None:
        """Create a git branch and add a stub commit for the suggestion."""
        repo_root = self._factory_root.parent
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )
        # Create a stub file documenting the suggestion
        stub_path = repo_root / "artifacts" / "self-research" / f"{suggestion.id}.md"
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        stub_path.write_text(
            f"# Suggestion {suggestion.id}: {suggestion.title}\n\n"
            f"**Category**: {suggestion.category}\n"
            f"**Risk**: {suggestion.risk_level}\n\n"
            f"## Description\n{suggestion.description}\n\n"
            f"## Expected Impact\n{suggestion.expected_impact}\n"
        )
        subprocess.run(
            ["git", "add", str(stub_path)],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"self-research: {suggestion.title[:60]}"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )

    async def _get_report_by_id(self, report_id: int) -> SelfResearchReport | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SelfResearchReport).where(SelfResearchReport.id == report_id)
            )
            return result.scalar_one_or_none()
