"""Structured audit logging for factory pipeline."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import structlog

logger = structlog.get_logger()


class AuditLogger:
    def __init__(self, report_path: str) -> None:
        self._path = Path(report_path)
        self._entries: list[str] = []

    def log_phase_start(
        self,
        phase: int,
        phase_name: str,
        models_used: list[dict],
        tier: int,
    ) -> None:
        entry = (
            f"\n## Phase {phase}: {phase_name}\n"
            f"- **Timestamp**: {datetime.utcnow().isoformat()}\n"
            f"- **Tier**: {tier}\n\n"
            "### Models Used\n"
        )
        for m in models_used:
            entry += (
                f"| {m.get('model', '')} "
                f"| {m.get('provider', '')} "
                f"| {m.get('via', '')} "
                f"| {m.get('role', '')} |\n"
            )
        self._entries.append(entry)
        logger.info("audit_phase_start", phase=phase, name=phase_name)

    def log_phase_end(
        self,
        phase: int,
        quality_score: int | None,
        duration_seconds: int,
    ) -> None:
        entry = (
            f"\n### Quality Gate\n"
            f"- **Score**: {quality_score}/100\n"
            f"- **Duration**: {duration_seconds}s\n"
        )
        self._entries.append(entry)

    def log_model_call(
        self,
        provider: str,
        model: str,
        role: str,
        tokens_in: int,
        tokens_out: int,
        cost: float,
    ) -> None:
        entry = (
            f"| {model} "
            f"| {provider} "
            f"| {role} "
            f"| ~{tokens_in} in + ~{tokens_out} out "
            f"| ~${cost:.2f} |\n"
        )
        self._entries.append(entry)

    def log_decision(self, decision: str, rationale: str) -> None:
        entry = (
            f"\n### Decision: {decision}\n"
            f"- **Rationale**: {rationale}\n"
        )
        self._entries.append(entry)

    def generate_summary(self) -> str:
        return "\n".join(self._entries)

    def flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            f.write("\n".join(self._entries))
        self._entries.clear()
