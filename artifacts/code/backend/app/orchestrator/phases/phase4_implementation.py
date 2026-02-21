"""Phase 4: Implementation + Testing (with Information Barrier) implementation.

Manages Backend Implementer, Frontend Implementer, and Black Box Tester agents
under strict information barrier rules.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from app.orchestrator.information_barrier import InformationBarrier

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger()

_barrier = InformationBarrier()

# ── System Prompts ────────────────────────────────────────────────────────────

_BACKEND_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior backend engineer. Your task is to implement the complete backend
    based on the spec.md, design.md, and interfaces.md provided.

    Rules:
    - Implement ALL endpoints and data models specified in interfaces.md
    - Follow the architecture patterns in design.md exactly
    - Use Python 3.11+, SQLAlchemy 2.0 async, FastAPI, pydantic-settings, structlog
    - Every function must have type annotations
    - Include comprehensive docstrings
    - Handle all error cases defined in the spec
    - Do NOT reference or invent test files
    - Do NOT look at or create frontend code

    Output: Complete Python source files, ready to run.
    Format each file as:
    ### FILE: <relative_path>
    ```python
    <content>
    ```
""")

_FRONTEND_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a senior frontend engineer. Your task is to implement the complete frontend
    based on the spec.md and interfaces.md provided.

    Rules:
    - Implement ALL UI screens and flows described in the spec
    - Use the API contract in interfaces.md exactly — no assumptions
    - Do NOT reference or look at backend implementation code
    - Do NOT reference or look at test files

    Output: Complete frontend source files.
    Format each file as:
    ### FILE: <relative_path>
    ```
    <content>
    ```
""")

_TESTER_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a black box QA engineer. You can ONLY see the spec.md and interfaces.md.
    You have NO access to the backend or frontend implementation code.

    Your task: Write comprehensive black-box tests that verify the API contract.

    Rules:
    - Test ONLY the public API as defined in interfaces.md
    - Use pytest + httpx (async) for backend API tests
    - Cover: happy paths, validation errors, auth failures, edge cases
    - Do NOT peek at any implementation files
    - Do NOT make assumptions about internal implementation details

    Output: Complete Python test files.
    Format each file as:
    ### FILE: <relative_path>
    ```python
    <content>
    ```
""")


def _parse_file_blocks(llm_output: str) -> dict[str, str]:
    """Parse ### FILE: <path> + code fence blocks from LLM output."""
    import re

    files: dict[str, str] = {}
    pattern = re.compile(
        r"###\s+FILE:\s+(?P<path>[^\n]+)\n```[^\n]*\n(?P<content>.*?)```",
        re.DOTALL,
    )
    for match in pattern.finditer(llm_output):
        rel_path = match.group("path").strip()
        content = match.group("content")
        files[rel_path] = content

    return files


def _write_files(base_dir: Path, files: dict[str, str]) -> list[str]:
    """Write parsed files to disk, returning a list of written paths."""
    written: list[str] = []
    for rel_path, content in files.items():
        dest = base_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        written.append(str(dest))
    return written


class Phase4ImplementationExecutor:
    """Executes Phase 4 of the factory pipeline: implementation + black-box testing."""

    PHASE_NUMBER = 4
    PHASE_NAME = "implementation_and_testing"

    async def execute(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        """Execute this phase. Returns result dict with artifacts produced."""
        logger.info("phase_4_started", run_id=str(run_id))
        result = await self._run(run_id, context)
        logger.info("phase_4_completed", run_id=str(run_id))
        return result

    async def _run(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        project_dir = Path(context.get("project_dir", ""))
        spec_path = project_dir / "artifacts" / "requirements" / "spec.md"
        design_path = project_dir / "artifacts" / "architecture" / "design.md"
        interfaces_path = project_dir / "artifacts" / "architecture" / "interfaces.md"
        backend_dir = project_dir / "artifacts" / "code" / "backend"
        frontend_dir = project_dir / "artifacts" / "code" / "frontend"
        tests_dir = project_dir / "artifacts" / "tests"

        if not spec_path.exists():
            raise FileNotFoundError(f"spec.md not found at {spec_path}")
        if not interfaces_path.exists():
            raise FileNotFoundError(f"interfaces.md not found at {interfaces_path}")

        spec_content = spec_path.read_text(encoding="utf-8")
        interfaces_content = interfaces_path.read_text(encoding="utf-8")
        design_content = (
            design_path.read_text(encoding="utf-8") if design_path.exists() else ""
        )

        provider_registry = context.get("provider_registry")
        tier = context.get("tier", 2)
        model_assignments = context.get("model_assignments", {})

        # ── Backend Implementer (BLOCKED from tests/) ──────────────────────
        logger.info("phase_4_backend_start", run_id=str(run_id))
        backend_files = await self._run_backend_implementer(
            spec_content=spec_content,
            design_content=design_content,
            interfaces_content=interfaces_content,
            provider_registry=provider_registry,
            tier=tier,
        )
        written_backend = _write_files(backend_dir, backend_files)
        logger.info(
            "phase_4_backend_done",
            run_id=str(run_id),
            files_written=len(written_backend),
        )

        # ── Frontend Implementer (BLOCKED from tests/ and backend/) ───────
        logger.info("phase_4_frontend_start", run_id=str(run_id))
        frontend_files = await self._run_frontend_implementer(
            spec_content=spec_content,
            interfaces_content=interfaces_content,
            provider_registry=provider_registry,
            model_assignments=model_assignments,
            tier=tier,
        )
        written_frontend = _write_files(frontend_dir, frontend_files)
        logger.info(
            "phase_4_frontend_done",
            run_id=str(run_id),
            files_written=len(written_frontend),
        )

        # ── Black Box Tester (BLOCKED from code/) ────────────────────────
        logger.info("phase_4_tester_start", run_id=str(run_id))
        test_files = await self._run_black_box_tester(
            spec_content=spec_content,
            interfaces_content=interfaces_content,
            provider_registry=provider_registry,
            model_assignments=model_assignments,
            tier=tier,
        )
        written_tests = _write_files(tests_dir, test_files)
        logger.info(
            "phase_4_tester_done",
            run_id=str(run_id),
            files_written=len(written_tests),
        )

        return {
            "phase": self.PHASE_NUMBER,
            "phase_name": self.PHASE_NAME,
            "status": "completed",
            "artifacts": {
                "backend_files": written_backend,
                "frontend_files": written_frontend,
                "test_files": written_tests,
            },
            "tier": tier,
        }

    async def _run_backend_implementer(
        self,
        spec_content: str,
        design_content: str,
        interfaces_content: str,
        provider_registry: Any,
        tier: int,
    ) -> dict[str, str]:
        """Generate backend code (blocked from test knowledge)."""
        # INFORMATION BARRIER: implementer only reads spec, design, interfaces
        allowed_artifacts = {
            "spec.md": spec_content,
            "design.md": design_content,
            "interfaces.md": interfaces_content,
        }
        # Validate barrier compliance
        for path in allowed_artifacts:
            assert _barrier.validate_access("implementer", f"artifacts/requirements/{path}", "read") or \
                   _barrier.validate_access("implementer", f"artifacts/architecture/{path}", "read"), \
                   f"Barrier violation: implementer tried to access {path}"

        user_content = (
            f"## spec.md\n\n{spec_content}\n\n"
            f"## design.md\n\n{design_content}\n\n"
            f"## interfaces.md\n\n{interfaces_content}"
        )
        messages = [
            {"role": "system", "content": _BACKEND_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        output = await self._call_implementer(messages, provider_registry, tier)
        return _parse_file_blocks(output)

    async def _run_frontend_implementer(
        self,
        spec_content: str,
        interfaces_content: str,
        provider_registry: Any,
        model_assignments: dict,
        tier: int,
    ) -> dict[str, str]:
        """Generate frontend code (blocked from backend code and tests)."""
        user_content = (
            f"## spec.md\n\n{spec_content}\n\n"
            f"## interfaces.md\n\n{interfaces_content}"
        )
        messages = [
            {"role": "system", "content": _FRONTEND_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        # Frontend uses Gemini per tier routing
        frontend_config = model_assignments.get(
            "frontend_implementer",
            {"provider": "google_ai", "model": "gemini-2.0-flash"},
        )
        output = await self._call_model(
            messages, provider_registry,
            preferred_provider=frontend_config.get("provider", "google_ai"),
            preferred_model=frontend_config.get("model"),
        )
        return _parse_file_blocks(output)

    async def _run_black_box_tester(
        self,
        spec_content: str,
        interfaces_content: str,
        provider_registry: Any,
        model_assignments: dict,
        tier: int,
    ) -> dict[str, str]:
        """Generate black-box tests (BLOCKED from all code)."""
        # INFORMATION BARRIER: tester only sees spec + interfaces
        user_content = (
            f"## spec.md\n\n{spec_content}\n\n"
            f"## interfaces.md\n\n{interfaces_content}"
        )
        messages = [
            {"role": "system", "content": _TESTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        tester_config = model_assignments.get(
            "black_box_tester",
            {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        )
        output = await self._call_model(
            messages, provider_registry,
            preferred_provider=tester_config.get("provider", "groq"),
            preferred_model=tester_config.get("model"),
        )
        return _parse_file_blocks(output)

    async def _call_implementer(
        self, messages: list[dict], provider_registry: Any, tier: int
    ) -> str:
        """Call the backend implementer LLM (prefer large-context providers)."""
        return await self._call_model(
            messages, provider_registry,
            preferred_provider="google_ai",
            fallback_providers=["groq", "cerebras", "sambanova"],
        )

    async def _call_model(
        self,
        messages: list[dict],
        provider_registry: Any,
        preferred_provider: str = "google_ai",
        preferred_model: str | None = None,
        fallback_providers: list[str] | None = None,
    ) -> str:
        """Try the preferred provider, then fall back through alternatives."""
        if provider_registry is None:
            logger.warning("no_provider_registry_returning_stub")
            return ""

        providers_to_try = [preferred_provider] + (fallback_providers or [
            "groq", "google_ai", "cerebras", "sambanova"
        ])
        # Deduplicate while preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for p in providers_to_try:
            if p not in seen:
                ordered.append(p)
                seen.add(p)

        for provider_name in ordered:
            if provider_name not in provider_registry:
                continue
            try:
                adapter = provider_registry.get_provider(provider_name)
                models = await adapter.list_models()
                if not models:
                    continue
                if preferred_model:
                    model_obj = next(
                        (m for m in models if m.name == preferred_model), models[0]
                    )
                else:
                    model_obj = sorted(
                        models, key=lambda m: m.context_window, reverse=True
                    )[0]
                response = await adapter.chat_completion(
                    model=model_obj.name,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=8192,
                    timeout=300.0,
                )
                logger.info(
                    "implementation_call_succeeded",
                    provider=provider_name,
                    model=model_obj.name,
                )
                return response.content
            except Exception as exc:
                logger.warning(
                    "implementation_call_failed",
                    provider=provider_name,
                    error=str(exc),
                )

        return ""
