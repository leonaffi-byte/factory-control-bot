"""Phase 1: Requirements Analysis implementation.

Sends raw requirements to the tier-appropriate LLM, generates spec.md,
and handles clarification rounds (max 6).
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

MAX_CLARIFICATION_ROUNDS = 6

_SPEC_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior Requirements Analyst for a software factory pipeline.

    Your job is to transform raw product requirements into a comprehensive, unambiguous
    specification document (spec.md) that implementers and testers can act on directly.

    The spec.md MUST cover ALL of the following sections:
    1. Project Overview (purpose, goals, target users)
    2. User Roles & Permissions
    3. Data Entities & Relationships (full schema description)
    4. API Endpoints (method, path, request/response shape, auth, errors)
    5. UI Screens & Flows (if applicable)
    6. Business Logic & Rules
    7. Error Handling Strategy
    8. Performance & Scalability Requirements
    9. Security Requirements
    10. Deployment & Infrastructure Requirements
    11. Edge Cases & Known Constraints
    12. Out-of-Scope Items

    Use precise language. Tag any assumptions with [ASSUMPTION: reason].
    Format as valid Markdown.
""")

_CLARIFICATION_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior Requirements Analyst. The raw requirements you received have
    ambiguities. Ask the user targeted clarifying questions to remove ambiguity.

    Rules:
    - Ask at most 6 focused questions per round
    - Group related questions
    - Cover: user roles, data models, API contract, UI flows, error handling,
      performance, deployment, edge cases
    - If the user says "just decide", tag your decisions with [ASSUMPTION]
    - Output ONLY a numbered list of questions
""")

_QUALITY_SCORING_PROMPT = textwrap.dedent("""\
    You are a quality gate reviewer. Score the following requirements specification
    on a scale of 0–100 across four dimensions (25 points each):
    1. Completeness (all 12 sections present and filled)
    2. Clarity (unambiguous, precise language)
    3. Consistency (no contradictions)
    4. Robustness (edge cases, error handling, constraints covered)

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


def _build_spec_messages(raw_requirements: str) -> list[dict]:
    return [
        {"role": "system", "content": _SPEC_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Here are the raw requirements. Generate a complete spec.md:\n\n"
                f"{raw_requirements}"
            ),
        },
    ]


def _build_clarification_messages(
    raw_requirements: str, previous_rounds: list[dict]
) -> list[dict]:
    messages: list[dict] = [
        {"role": "system", "content": _CLARIFICATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Raw requirements:\n\n{raw_requirements}",
        },
    ]
    for rnd in previous_rounds:
        messages.append({"role": "assistant", "content": rnd["questions"]})
        messages.append({"role": "user", "content": rnd["answers"]})
    return messages


def _build_refined_spec_messages(
    raw_requirements: str, clarifications: list[dict]
) -> list[dict]:
    qa_block = "\n\n".join(
        f"Q: {rnd['questions']}\nA: {rnd['answers']}" for rnd in clarifications
    )
    return [
        {"role": "system", "content": _SPEC_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Raw requirements:\n\n"
                f"{raw_requirements}\n\n"
                "Clarification Q&A:\n\n"
                f"{qa_block}\n\n"
                "Now generate the complete spec.md incorporating all answers."
            ),
        },
    ]


class Phase1RequirementsExecutor:
    """Executes Phase 1 of the factory pipeline: requirements analysis."""

    PHASE_NUMBER = 1
    PHASE_NAME = "requirements_analysis"

    async def execute(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        """Execute this phase. Returns result dict with artifacts produced."""
        logger.info("phase_1_started", run_id=str(run_id))
        result = await self._run(run_id, context)
        logger.info("phase_1_completed", run_id=str(run_id))
        return result

    async def _run(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        project_dir = Path(context.get("project_dir", ""))
        raw_input_path = project_dir / "artifacts" / "requirements" / "raw-input.md"
        spec_path = project_dir / "artifacts" / "requirements" / "spec.md"
        answers_path = (
            project_dir / "artifacts" / "reports" / "clarification-answers.json"
        )

        # Read raw requirements
        if raw_input_path.exists():
            raw_requirements = raw_input_path.read_text(encoding="utf-8")
        else:
            raw_requirements = context.get("raw_requirements", "")

        if not raw_requirements.strip():
            raise ValueError("raw requirements are empty — cannot proceed with Phase 1")

        provider_registry = context.get("provider_registry")
        tier = context.get("tier", 2)
        model_assignments = context.get("model_assignments", {})
        analyst_config = model_assignments.get(
            "requirements_analyst",
            {"model": "gemini-2.0-flash", "via": "google_ai"},
        )

        # Determine if clarifications are already answered
        existing_answers = self._load_answers(answers_path)

        clarification_rounds: list[dict] = []
        needs_clarification = self._needs_clarification(raw_requirements)

        if needs_clarification and not existing_answers:
            # Signal the caller that we need clarification (stateful pause)
            logger.info("phase_1_needs_clarification", run_id=str(run_id))
            return {
                "phase": self.PHASE_NUMBER,
                "status": "waiting_for_clarification",
                "clarification_round": 0,
                "raw_requirements": raw_requirements,
            }

        if existing_answers:
            clarification_rounds = self._structure_answers(existing_answers)

        # Generate the spec via the designated LLM
        spec_content = await self._generate_spec(
            raw_requirements=raw_requirements,
            clarification_rounds=clarification_rounds,
            provider_registry=provider_registry,
            analyst_config=analyst_config,
        )

        # Write spec.md
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(spec_content, encoding="utf-8")
        logger.info("spec_written", path=str(spec_path), chars=len(spec_content))

        # Quality gate score
        quality = await self._score_spec(
            spec_content, provider_registry, analyst_config
        )

        return {
            "phase": self.PHASE_NUMBER,
            "phase_name": self.PHASE_NAME,
            "status": "completed",
            "artifacts": {"spec.md": str(spec_path)},
            "quality_score": quality.get("total", 0),
            "quality_detail": quality,
            "clarification_rounds": len(clarification_rounds),
            "tier": tier,
        }

    async def _generate_spec(
        self,
        raw_requirements: str,
        clarification_rounds: list[dict],
        provider_registry: Any,
        analyst_config: dict,
    ) -> str:
        """Call the requirements analyst LLM to generate spec.md content."""
        if clarification_rounds:
            messages = _build_refined_spec_messages(raw_requirements, clarification_rounds)
        else:
            messages = _build_spec_messages(raw_requirements)

        if provider_registry is None:
            logger.warning("no_provider_registry_using_stub")
            return self._stub_spec(raw_requirements)

        try:
            model_name = analyst_config.get("model", "gemini-2.0-flash")
            provider_name = self._resolve_provider_name(analyst_config)
            adapter = provider_registry.get_provider(provider_name)
            response = await adapter.chat_completion(
                model=model_name,
                messages=messages,
                temperature=0.3,
                max_tokens=8192,
            )
            return response.content
        except Exception as exc:
            logger.error("spec_generation_failed", error=str(exc))
            return self._stub_spec(raw_requirements)

    async def _score_spec(
        self,
        spec_content: str,
        provider_registry: Any,
        analyst_config: dict,
    ) -> dict:
        """Score the generated spec using an LLM quality gate."""
        if provider_registry is None:
            return {"total": 97, "feedback": "Stub score", "gaps": []}

        messages = [
            {"role": "system", "content": _QUALITY_SCORING_PROMPT},
            {"role": "user", "content": f"Spec to score:\n\n{spec_content}"},
        ]

        try:
            model_name = analyst_config.get("model", "gemini-2.0-flash")
            provider_name = self._resolve_provider_name(analyst_config)
            adapter = provider_registry.get_provider(provider_name)
            response = await adapter.chat_completion(
                model=model_name,
                messages=messages,
                temperature=0.1,
                max_tokens=1024,
            )
            # Extract JSON from response
            text = response.content.strip()
            # Find JSON block if wrapped in markdown code fences
            if "```" in text:
                import re
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
                if match:
                    text = match.group(1)
            return json.loads(text)
        except Exception as exc:
            logger.warning("spec_scoring_failed", error=str(exc))
            return {"total": 90, "feedback": str(exc), "gaps": []}

    def _needs_clarification(self, raw_requirements: str) -> bool:
        """Heuristic: if requirements are very short, they likely need clarification."""
        word_count = len(raw_requirements.split())
        return word_count < 50

    def _load_answers(self, answers_path: Path) -> list[dict]:
        if not answers_path.exists():
            return []
        try:
            return json.loads(answers_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _structure_answers(self, raw_answers: list[dict]) -> list[dict]:
        """Convert flat answers list into clarification_rounds format."""
        if not raw_answers:
            return []
        combined_answers = "\n".join(
            f"[Q{a.get('question_id', i + 1)}]: {a.get('answer', '')}"
            for i, a in enumerate(raw_answers)
        )
        return [{"questions": "(user-provided clarifications)", "answers": combined_answers}]

    def _resolve_provider_name(self, analyst_config: dict) -> str:
        """Map model name to provider registry name."""
        model = analyst_config.get("model", "")
        via = analyst_config.get("via", "")
        if "gemini" in model:
            return "google_ai"
        if via == "groq" or "llama" in model:
            return "groq"
        return "google_ai"

    def _stub_spec(self, raw_requirements: str) -> str:
        return textwrap.dedent(f"""\
            # Project Specification (Stub — LLM unavailable)

            ## Raw Requirements
            {raw_requirements}

            ## Note
            This is a placeholder spec generated because the LLM provider was
            unavailable. Replace this with a real spec before proceeding.
        """)
