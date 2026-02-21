"""Phase 0: Complexity Assessment implementation.

Reads raw-input.md, counts signals, and selects Tier 1/2/3 model routing.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger()

# Tier thresholds based on signal counts
_TIER_SIGNALS: dict[str, dict] = {
    "endpoints": {"tier2_min": 5, "tier3_min": 20},
    "entities": {"tier2_min": 3, "tier3_min": 8},
    "integrations": {"tier2_min": 1, "tier3_min": 3},
}

# Keyword patterns that signal higher complexity
_TIER3_KEYWORDS = frozenset([
    "microservice", "distributed", "real-time", "realtime", "fpga", "embedded",
    "websocket", "event-driven", "kafka", "rabbitmq", "kubernetes", "k8s",
    "multi-tenant", "sharding", "cqrs", "event sourcing",
])
_TIER2_KEYWORDS = frozenset([
    "auth", "authentication", "oauth", "jwt", "rbac", "dashboard",
    "analytics", "webhook", "background job", "celery", "worker", "notification",
    "email", "payment", "stripe", "role",
])

# Model assignments per tier
_TIER_MODELS: dict[int, dict] = {
    1: {
        "requirements_analyst": {"model": "gemini-2.5-flash", "via": "zen"},
        "architect": {"model": "claude-sonnet-4-6", "via": "native"},
        "backend_implementer": {"model": "claude-sonnet-4-6", "via": "task"},
        "frontend_implementer": {"model": "gemini-2.5-flash", "via": "zen"},
        "black_box_tester": {"model": "qwen3", "via": "zen"},
        "code_reviewer": {"model": "gpt-5.2", "via": "zen"},
        "security_auditor": {"model": "gemini-2.5-flash", "via": "zen"},
        "docs_deployer": {"model": "claude-sonnet-4-6", "via": "task"},
        "estimated_cost": "$5-15",
    },
    2: {
        "requirements_analyst": {"model": "gemini-3-pro", "via": "zen"},
        "architect": {"model": "claude-opus-4-6", "via": "native"},
        "backend_implementer": {"model": "claude-sonnet-4-6", "via": "task"},
        "frontend_implementer": {"model": "gemini-3-pro", "via": "zen"},
        "black_box_tester": {"model": "gpt-5.2", "via": "zen"},
        "code_reviewer": {"model": "o3", "via": "zen"},
        "security_auditor": {"model": "gemini-3-pro", "via": "zen"},
        "research_agent": {"model": "sonar-pro", "via": "perplexity"},
        "docs_deployer": {"model": "claude-sonnet-4-6", "via": "task"},
        "estimated_cost": "$20-50",
    },
    3: {
        "requirements_analyst": {"model": "gemini-3-pro", "via": "zen"},
        "architect": {"model": "claude-opus-4-6", "via": "native"},
        "backend_implementer": {"model": "claude-sonnet-4-6", "via": "task"},
        "frontend_implementer": {"model": "gemini-3-pro", "via": "zen"},
        "embedded_implementer": {"model": "claude-sonnet-4-6", "via": "task"},
        "black_box_tester": {"model": "gpt-5.2", "via": "zen"},
        "code_reviewer": {"model": "o3", "via": "zen"},
        "security_auditor_primary": {"model": "gemini-3-pro", "via": "zen"},
        "security_auditor_secondary": {"model": "glm-5", "via": "zen"},
        "research_agent": {"model": "sonar-deep-research", "via": "perplexity"},
        "full_context_review": {"model": "kimi-2.5", "via": "zen"},
        "docs_deployer": {"model": "claude-sonnet-4-6", "via": "task"},
        "estimated_cost": "$40-80",
    },
}


def _count_pattern(text: str, patterns: list[str]) -> int:
    """Count occurrences of any pattern in the text (case-insensitive)."""
    count = 0
    lower = text.lower()
    for pattern in patterns:
        count += len(re.findall(pattern, lower))
    return count


def _estimate_endpoints(text: str) -> int:
    """Heuristic: count REST method mentions and path-like patterns."""
    method_pattern = r"\b(GET|POST|PUT|PATCH|DELETE|endpoint|route|api)\b"
    path_pattern = r"/[a-z][a-z0-9_/{}]*"
    method_hits = len(re.findall(method_pattern, text, re.IGNORECASE))
    path_hits = len(re.findall(path_pattern, text))
    return max(method_hits // 2, path_hits)


def _estimate_entities(text: str) -> int:
    """Heuristic: count data model/table mentions."""
    patterns = [
        r"\b(model|entity|table|schema|record|object)\b",
        r"\b(user|project|order|product|item|event|log|task|session|token)\b",
    ]
    return _count_pattern(text, patterns)


def _estimate_integrations(text: str) -> int:
    """Heuristic: count third-party service mentions."""
    patterns = [
        r"\b(stripe|twilio|sendgrid|aws|gcp|azure|s3|sqs|sns|redis|rabbit|kafka)\b",
        r"\b(oauth|sso|ldap|webhook|external api|third.party|integration)\b",
    ]
    return _count_pattern(text, patterns)


def _has_realtime(text: str) -> bool:
    patterns = [
        r"\b(websocket|real.?time|live|streaming|push notification|server.sent event)\b"
    ]
    return _count_pattern(text, patterns) > 0


def _has_embedded_or_fpga(text: str) -> bool:
    patterns = [r"\b(fpga|embedded|firmware|microcontroller|arduino|raspberry pi|rtos)\b"]
    return _count_pattern(text, patterns) > 0


def _select_tier(
    endpoints: int,
    entities: int,
    integrations: int,
    realtime: bool,
    embedded: bool,
    keyword_tier2: int,
    keyword_tier3: int,
) -> tuple[int, str]:
    """Determine the complexity tier and produce a rationale string."""
    reasons: list[str] = []

    # Immediate Tier 3 triggers
    if embedded or (endpoints >= _TIER_SIGNALS["endpoints"]["tier3_min"]):
        if embedded:
            reasons.append("embedded/FPGA components detected")
        if endpoints >= _TIER_SIGNALS["endpoints"]["tier3_min"]:
            reasons.append(f"~{endpoints} endpoints (>= 20)")
        if realtime:
            reasons.append("real-time requirements")
        return 3, "Tier 3 selected: " + "; ".join(reasons)

    if realtime:
        reasons.append("real-time requirements")
        return 3, "Tier 3 selected: " + "; ".join(reasons)

    if integrations >= _TIER_SIGNALS["integrations"]["tier3_min"]:
        reasons.append(f"~{integrations} external integrations (>= 3)")
        return 3, "Tier 3 selected: " + "; ".join(reasons)

    if keyword_tier3 >= 2:
        reasons.append(f"{keyword_tier3} Tier-3 complexity keywords found")
        return 3, "Tier 3 selected: " + "; ".join(reasons)

    # Tier 2 signals
    if endpoints >= _TIER_SIGNALS["endpoints"]["tier2_min"]:
        reasons.append(f"~{endpoints} endpoints (>= 5)")
    if entities >= _TIER_SIGNALS["entities"]["tier2_min"]:
        reasons.append(f"~{entities} data entities (>= 3)")
    if integrations >= _TIER_SIGNALS["integrations"]["tier2_min"]:
        reasons.append(f"~{integrations} external integrations (>= 1)")
    if keyword_tier2 >= 2:
        reasons.append(f"{keyword_tier2} Tier-2 complexity keywords found")

    if reasons:
        return 2, "Tier 2 selected: " + "; ".join(reasons)

    return 1, "Tier 1 selected: simple project with few endpoints, entities, and no real-time needs"


class Phase0AssessmentExecutor:
    """Executes Phase 0 of the factory pipeline: complexity assessment and tier selection."""

    PHASE_NUMBER = 0
    PHASE_NAME = "complexity_assessment"

    async def execute(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        """Execute this phase. Returns result dict with artifacts produced."""
        logger.info("phase_0_started", run_id=str(run_id))
        result = await self._run(run_id, context)
        logger.info(
            "phase_0_completed",
            run_id=str(run_id),
            tier=result.get("tier"),
        )
        return result

    async def _run(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        """Read raw-input.md, count signals, select tier, return assessment."""
        project_dir = context.get("project_dir", "")
        raw_input_path = Path(project_dir) / "artifacts" / "requirements" / "raw-input.md"

        if not raw_input_path.exists():
            logger.warning("raw_input_not_found", path=str(raw_input_path))
            raw_text = context.get("raw_requirements", "")
        else:
            raw_text = raw_input_path.read_text(encoding="utf-8")

        lower_text = raw_text.lower()

        # Count complexity signals
        endpoints = _estimate_endpoints(raw_text)
        entities = _estimate_entities(raw_text)
        integrations = _estimate_integrations(raw_text)
        realtime = _has_realtime(raw_text)
        embedded = _has_embedded_or_fpga(raw_text)

        keyword_tier3 = sum(1 for kw in _TIER3_KEYWORDS if kw in lower_text)
        keyword_tier2 = sum(1 for kw in _TIER2_KEYWORDS if kw in lower_text)

        tier, rationale = _select_tier(
            endpoints=endpoints,
            entities=entities,
            integrations=integrations,
            realtime=realtime,
            embedded=embedded,
            keyword_tier2=keyword_tier2,
            keyword_tier3=keyword_tier3,
        )

        model_assignments = _TIER_MODELS[tier]

        signals = {
            "estimated_endpoints": endpoints,
            "estimated_entities": entities,
            "estimated_integrations": integrations,
            "has_realtime": realtime,
            "has_embedded": embedded,
            "tier2_keywords_count": keyword_tier2,
            "tier3_keywords_count": keyword_tier3,
        }

        logger.info(
            "complexity_assessed",
            run_id=str(run_id),
            tier=tier,
            rationale=rationale,
            **signals,
        )

        return {
            "tier": tier,
            "rationale": rationale,
            "signals": signals,
            "model_assignments": model_assignments,
            "phase": self.PHASE_NUMBER,
            "phase_name": self.PHASE_NAME,
        }
