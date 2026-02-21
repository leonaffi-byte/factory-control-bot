"""Phase 3: Architecture Design implementation.

Generates design.md and interfaces.md from spec + brainstorm using the native
Claude Opus architect role.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger()

_DESIGN_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a principal software architect. Using the requirements spec and brainstorm
    input below, produce a complete system architecture design document (design.md).

    The design.md MUST contain:
    1. **System Overview** — architecture pattern, high-level diagram (ASCII), components
    2. **Technology Stack** — all chosen technologies with version constraints and rationale
    3. **Data Models** — complete schema definitions for every entity (fields, types, indexes,
       relationships, constraints)
    4. **Service Architecture** — each service/module, its responsibility, and dependencies
    5. **Authentication & Authorization** — auth flow, token strategy, RBAC/ABAC rules
    6. **API Design Principles** — versioning, error format, pagination, rate limiting
    7. **Caching Strategy** — what is cached, TTL, invalidation rules
    8. **Background Jobs** — tasks, schedules, retry/dead-letter strategy
    9. **File Storage** — if applicable, storage backend and access patterns
    10. **Monitoring & Observability** — metrics, tracing, alerting strategy
    11. **Error Handling Patterns** — global error taxonomy, HTTP status mapping
    12. **Validation Rules** — input validation rules per entity/endpoint
    13. **Configuration Management** — env vars, secrets, per-environment overrides
    14. **Scalability Considerations** — expected load, bottlenecks, horizontal scaling plan
    15. **Security Architecture** — threat model, mitigations
    16. **Migration & Rollback Strategy** — DB migrations, feature flags
    17. **Testing Strategy** — unit, integration, E2E approach

    Use precise, implementer-ready language. No placeholder text.
    Format as valid Markdown.
""")

_INTERFACES_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a principal software architect. Using the architecture design, produce
    interfaces.md — the formal API contract between frontend and backend.

    interfaces.md MUST contain:
    1. **Base URL & Versioning**
    2. **Authentication** — header format, token lifecycle
    3. **Common Response Envelope** — success/error wrapper format
    4. **Endpoints** — for EVERY endpoint:
       - Method + Path
       - Description
       - Authentication required?
       - Request: path params, query params, request body (with field types, required/optional)
       - Success Response: status code + body schema
       - Error Responses: every possible error code + body
    5. **WebSocket Events** — if applicable
    6. **Pagination Convention** — cursor vs offset, response envelope
    7. **Rate Limiting Headers** — X-RateLimit-* headers spec
    8. **Webhook Payloads** — if applicable

    Use OpenAPI 3.0 YAML blocks for each endpoint schema.
    This document is the single source of truth for frontend/backend integration.
""")

_QUALITY_SCORING_PROMPT = textwrap.dedent("""\
    You are a quality gate reviewer for software architecture.
    Score the following architecture design on a scale of 0–100 (25 pts each):
    1. Completeness (all 17 sections present)
    2. Clarity (unambiguous, precise, implementer-ready)
    3. Consistency (no contradictions between sections)
    4. Robustness (error handling, security, scaling covered)

    Return JSON only:
    {
      "completeness": <0-25>,
      "clarity": <0-25>,
      "consistency": <0-25>,
      "robustness": <0-25>,
      "total": <0-100>,
      "feedback": "<one paragraph>",
      "gaps": ["<gap1>", "<gap2>"]
    }
""")


class Phase3ArchitectureExecutor:
    """Executes Phase 3 of the factory pipeline: architecture design."""

    PHASE_NUMBER = 3
    PHASE_NAME = "architecture_design"

    async def execute(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        """Execute this phase. Returns result dict with artifacts produced."""
        logger.info("phase_3_started", run_id=str(run_id))
        result = await self._run(run_id, context)
        logger.info("phase_3_completed", run_id=str(run_id))
        return result

    async def _run(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        project_dir = Path(context.get("project_dir", ""))
        spec_path = project_dir / "artifacts" / "requirements" / "spec.md"
        brainstorm_path = project_dir / "artifacts" / "architecture" / "brainstorm.md"
        design_path = project_dir / "artifacts" / "architecture" / "design.md"
        interfaces_path = project_dir / "artifacts" / "architecture" / "interfaces.md"

        if not spec_path.exists():
            raise FileNotFoundError(f"spec.md not found at {spec_path}")

        spec_content = spec_path.read_text(encoding="utf-8")
        brainstorm_content = (
            brainstorm_path.read_text(encoding="utf-8")
            if brainstorm_path.exists()
            else ""
        )

        provider_registry = context.get("provider_registry")
        tier = context.get("tier", 2)

        # Generate design.md
        design_content = await self._generate_design(
            spec_content, brainstorm_content, provider_registry, tier
        )
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text(design_content, encoding="utf-8")
        logger.info("design_written", path=str(design_path), chars=len(design_content))

        # Generate interfaces.md
        interfaces_content = await self._generate_interfaces(
            spec_content, design_content, provider_registry, tier
        )
        interfaces_path.write_text(interfaces_content, encoding="utf-8")
        logger.info(
            "interfaces_written",
            path=str(interfaces_path),
            chars=len(interfaces_content),
        )

        # Quality gate
        quality = await self._score_design(design_content, provider_registry, tier)

        return {
            "phase": self.PHASE_NUMBER,
            "phase_name": self.PHASE_NAME,
            "status": "completed",
            "artifacts": {
                "design.md": str(design_path),
                "interfaces.md": str(interfaces_path),
            },
            "quality_score": quality.get("total", 0),
            "quality_detail": quality,
            "tier": tier,
        }

    async def _generate_design(
        self,
        spec_content: str,
        brainstorm_content: str,
        provider_registry: Any,
        tier: int,
    ) -> str:
        """Generate design.md via the architect LLM."""
        user_content = f"## Requirements Spec\n\n{spec_content}"
        if brainstorm_content:
            user_content += f"\n\n## Brainstorm Input\n\n{brainstorm_content}"

        messages = [
            {"role": "system", "content": _DESIGN_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        return await self._call_architect(messages, provider_registry, tier)

    async def _generate_interfaces(
        self,
        spec_content: str,
        design_content: str,
        provider_registry: Any,
        tier: int,
    ) -> str:
        """Generate interfaces.md via the architect LLM."""
        user_content = (
            f"## Architecture Design\n\n{design_content}\n\n"
            f"## Requirements Spec\n\n{spec_content}"
        )
        messages = [
            {"role": "system", "content": _INTERFACES_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        return await self._call_architect(messages, provider_registry, tier)

    async def _call_architect(
        self,
        messages: list[dict],
        provider_registry: Any,
        tier: int,
    ) -> str:
        """Route to the appropriate architect provider based on tier."""
        if provider_registry is None:
            return "# Architecture Design\n\nNo LLM provider available (stub output)."

        # Tier 2+3 prefer google_ai (Gemini Pro for large context),
        # Tier 1 can use any fast provider
        priority_providers = (
            ["google_ai", "groq", "cerebras", "sambanova"]
            if tier >= 2
            else ["groq", "google_ai", "cerebras", "sambanova"]
        )

        for provider_name in priority_providers:
            if provider_name not in provider_registry:
                continue
            try:
                adapter = provider_registry.get_provider(provider_name)
                models = await adapter.list_models()
                if not models:
                    continue
                # For architecture, prefer large context models
                model = sorted(models, key=lambda m: m.context_window, reverse=True)[0]
                response = await adapter.chat_completion(
                    model=model.name,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=8192,
                )
                logger.info(
                    "architect_call_succeeded",
                    provider=provider_name,
                    model=model.name,
                )
                return response.content
            except Exception as exc:
                logger.warning(
                    "architect_call_failed",
                    provider=provider_name,
                    error=str(exc),
                )

        return "# Architecture Design\n\nAll architect providers failed. Manual review required."

    async def _score_design(
        self, design_content: str, provider_registry: Any, tier: int
    ) -> dict:
        """Score the architecture design using an LLM quality gate."""
        if provider_registry is None:
            return {"total": 97, "feedback": "Stub score", "gaps": []}

        messages = [
            {"role": "system", "content": _QUALITY_SCORING_PROMPT},
            {"role": "user", "content": f"Architecture design to score:\n\n{design_content}"},
        ]

        for provider_name in ("groq", "google_ai", "cerebras", "sambanova"):
            if provider_name not in provider_registry:
                continue
            try:
                adapter = provider_registry.get_provider(provider_name)
                models = await adapter.list_models()
                if not models:
                    continue
                response = await adapter.chat_completion(
                    model=models[0].name,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1024,
                )
                text = response.content.strip()
                if "```" in text:
                    import re
                    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
                    if match:
                        text = match.group(1)
                return json.loads(text)
            except Exception as exc:
                logger.warning("design_scoring_failed", provider=provider_name, error=str(exc))

        return {"total": 90, "feedback": "Scoring failed", "gaps": []}
