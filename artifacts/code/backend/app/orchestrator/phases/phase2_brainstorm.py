"""Phase 2: Multi-Model Brainstorm implementation.

Sends the spec to 3+ models from different providers, synthesizes recommendations
into a unified brainstorm.md.
"""
from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger()

_BRAINSTORM_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior software architect participating in a multi-model design brainstorm.

    Given the requirements spec, provide your expert recommendations covering:
    1. **Tech Stack** — languages, frameworks, databases, infrastructure
    2. **Architecture Pattern** — monolith vs microservices, event-driven, etc.
    3. **Data Storage** — schema design, indexing strategy, caching
    4. **API Design** — REST vs GraphQL vs gRPC, versioning, auth strategy
    5. **Key Risks** — scalability bottlenecks, security concerns, complexity traps
    6. **Alternatives Considered** — trade-offs you weighed
    7. **Estimated Effort** — rough team-weeks estimate

    Be specific and opinionated. Back recommendations with brief rationale.
    Format your response in Markdown with the sections above.
""")

_SYNTHESIS_PROMPT = textwrap.dedent("""\
    You are the Orchestrator synthesizing input from multiple AI architects.
    Below are their independent recommendations for the same project spec.

    Produce a unified brainstorm.md that:
    1. Identifies consensus recommendations (where 2+ models agree)
    2. Documents dissenting opinions and their trade-offs
    3. Provides a final unified recommendation for each decision area
    4. Lists open questions for the architect to resolve

    Format as Markdown. Be concise but thorough.
""")

# Provider assignment per tier for brainstorm phase
_TIER_BRAINSTORM_MODELS: dict[int, list[dict]] = {
    1: [
        {"provider": "google_ai", "model": "gemini-2.0-flash", "role": "Architect A"},
        {"provider": "groq", "model": "llama-3.3-70b-versatile", "role": "Architect B"},
        {"provider": "cerebras", "model": "llama3.3-70b", "role": "Architect C"},
    ],
    2: [
        {"provider": "google_ai", "model": "gemini-1.5-pro", "role": "Architect A"},
        {"provider": "groq", "model": "llama-3.3-70b-versatile", "role": "Architect B"},
        {"provider": "sambanova", "model": "Meta-Llama-3.3-70B-Instruct", "role": "Architect C"},
    ],
    3: [
        {"provider": "google_ai", "model": "gemini-1.5-pro", "role": "Architect A"},
        {"provider": "groq", "model": "deepseek-r1-distill-llama-70b", "role": "Architect B"},
        {"provider": "sambanova", "model": "Meta-Llama-3.3-70B-Instruct", "role": "Architect C"},
        {"provider": "cerebras", "model": "llama3.3-70b", "role": "Architect D"},
    ],
}


async def _get_one_opinion(
    provider_registry: Any,
    provider_name: str,
    model_name: str,
    role: str,
    spec_content: str,
) -> dict[str, str]:
    """Fetch one architect's opinion from the given provider/model."""
    messages = [
        {"role": "system", "content": _BRAINSTORM_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Requirements Specification:\n\n{spec_content}",
        },
    ]
    try:
        adapter = provider_registry.get_provider(provider_name)
        response = await adapter.chat_completion(
            model=model_name,
            messages=messages,
            temperature=0.6,
            max_tokens=4096,
        )
        return {
            "role": role,
            "provider": provider_name,
            "model": model_name,
            "content": response.content,
            "error": None,
        }
    except Exception as exc:
        logger.warning(
            "brainstorm_opinion_failed",
            provider=provider_name,
            model=model_name,
            error=str(exc),
        )
        return {
            "role": role,
            "provider": provider_name,
            "model": model_name,
            "content": "",
            "error": str(exc),
        }


def _format_brainstorm_doc(
    opinions: list[dict], synthesis: str, tier: int
) -> str:
    """Assemble the final brainstorm.md content."""
    sections: list[str] = [
        "# Phase 2: Multi-Model Architecture Brainstorm\n",
        f"**Tier**: {tier}  |  **Models**: {len(opinions)}\n",
        "---\n",
    ]

    for op in opinions:
        if op.get("error"):
            sections.append(
                f"## {op['role']} ({op['provider']} / {op['model']})\n"
                f"*ERROR: {op['error']}*\n"
            )
        else:
            sections.append(
                f"## {op['role']} ({op['provider']} / {op['model']})\n\n"
                f"{op['content']}\n"
            )

    sections.append("---\n\n## Synthesis\n\n")
    sections.append(synthesis)

    return "\n".join(sections)


class Phase2BrainstormExecutor:
    """Executes Phase 2 of the factory pipeline: multi-model brainstorm."""

    PHASE_NUMBER = 2
    PHASE_NAME = "brainstorm"

    async def execute(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        """Execute this phase. Returns result dict with artifacts produced."""
        logger.info("phase_2_started", run_id=str(run_id))
        result = await self._run(run_id, context)
        logger.info("phase_2_completed", run_id=str(run_id))
        return result

    async def _run(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        project_dir = Path(context.get("project_dir", ""))
        spec_path = project_dir / "artifacts" / "requirements" / "spec.md"
        brainstorm_path = project_dir / "artifacts" / "architecture" / "brainstorm.md"

        if not spec_path.exists():
            raise FileNotFoundError(f"spec.md not found at {spec_path}")

        spec_content = spec_path.read_text(encoding="utf-8")
        tier = context.get("tier", 2)
        provider_registry = context.get("provider_registry")

        # Select brainstorm models for this tier
        brainstorm_models = _TIER_BRAINSTORM_MODELS.get(tier, _TIER_BRAINSTORM_MODELS[2])

        # Filter to only providers that are available in the registry
        available_models: list[dict] = []
        for model_cfg in brainstorm_models:
            if provider_registry is not None and model_cfg["provider"] in provider_registry:
                available_models.append(model_cfg)
            else:
                logger.warning(
                    "brainstorm_provider_unavailable",
                    provider=model_cfg["provider"],
                    model=model_cfg["model"],
                )

        if not available_models and provider_registry is not None:
            # Fallback: try any available provider
            for info in provider_registry.get_enabled_providers():
                models = await provider_registry.get_provider(info.name).list_models()
                if models:
                    available_models.append({
                        "provider": info.name,
                        "model": models[0].name,
                        "role": f"Fallback Architect ({info.name})",
                    })
                if len(available_models) >= 2:
                    break

        # Gather opinions concurrently
        if available_models and provider_registry:
            tasks = [
                _get_one_opinion(
                    provider_registry,
                    m["provider"],
                    m["model"],
                    m["role"],
                    spec_content,
                )
                for m in available_models
            ]
            opinions = await asyncio.gather(*tasks)
        else:
            logger.warning("no_providers_for_brainstorm_using_stub")
            opinions = [
                {
                    "role": "Stub Architect",
                    "provider": "none",
                    "model": "stub",
                    "content": "No providers available. Manual brainstorm required.",
                    "error": None,
                }
            ]

        # Synthesize using first available provider
        synthesis = await self._synthesize(
            opinions=list(opinions),
            provider_registry=provider_registry,
        )

        # Write brainstorm.md
        brainstorm_path.parent.mkdir(parents=True, exist_ok=True)
        brainstorm_content = _format_brainstorm_doc(list(opinions), synthesis, tier)
        brainstorm_path.write_text(brainstorm_content, encoding="utf-8")
        logger.info(
            "brainstorm_written",
            path=str(brainstorm_path),
            models_used=len(opinions),
        )

        return {
            "phase": self.PHASE_NUMBER,
            "phase_name": self.PHASE_NAME,
            "status": "completed",
            "artifacts": {"brainstorm.md": str(brainstorm_path)},
            "models_used": [
                {"provider": op["provider"], "model": op["model"]} for op in opinions
            ],
            "tier": tier,
        }

    async def _synthesize(
        self, opinions: list[dict], provider_registry: Any
    ) -> str:
        """Use an available LLM to synthesize opinions into a unified recommendation."""
        if provider_registry is None:
            return "No providers available for synthesis."

        opinions_text = "\n\n---\n\n".join(
            f"### {op['role']} ({op['provider']})\n{op['content']}"
            for op in opinions
            if not op.get("error") and op.get("content")
        )
        if not opinions_text:
            return "All brainstorm opinions failed. Manual review required."

        messages = [
            {"role": "system", "content": _SYNTHESIS_PROMPT},
            {
                "role": "user",
                "content": f"Architect Opinions:\n\n{opinions_text}",
            },
        ]

        # Try providers in priority order for synthesis
        for provider_name in ("google_ai", "groq", "cerebras", "sambanova"):
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
                    temperature=0.3,
                    max_tokens=4096,
                )
                return response.content
            except Exception as exc:
                logger.warning("synthesis_failed", provider=provider_name, error=str(exc))

        return "Synthesis failed: all providers exhausted."
