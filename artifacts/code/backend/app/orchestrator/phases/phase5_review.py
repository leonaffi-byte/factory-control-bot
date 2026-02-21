"""Phase 5: Cross-Provider Review implementation.

Sends all code to a Code Reviewer (O3/GPT) and a Security Auditor (Gemini)
from different providers. Tier 3 also runs a Full Context Review (Kimi 2.5).
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger()

_CODE_REVIEW_PROMPT = textwrap.dedent("""\
    You are a principal engineer performing a comprehensive code review.
    Review the entire codebase for:

    1. **Correctness** — logic errors, off-by-one, null dereferences, race conditions
    2. **Code Quality** — readability, naming, DRY violations, dead code
    3. **Architecture Compliance** — does the code match the design.md spec?
    4. **Performance** — N+1 queries, blocking I/O in async context, memory leaks
    5. **Error Handling** — missing try/except, unhandled edge cases
    6. **Type Safety** — missing type hints, incorrect types
    7. **Security (basic)** — obvious injection points, hardcoded secrets
    8. **Testing Gaps** — untested code paths (without seeing the test files)

    For each issue, rate severity: CRITICAL | HIGH | MEDIUM | LOW
    Format:
    ## Issue #N [SEVERITY]: <Short title>
    **File**: <file_path>:<line_hint>
    **Description**: <what is wrong>
    **Fix**: <how to fix it>

    End with a summary table of issue counts by severity.
""")

_SECURITY_AUDIT_PROMPT = textwrap.dedent("""\
    You are a senior security engineer performing a thorough security audit.
    Review the codebase for:

    1. **Injection Vulnerabilities** — SQL, command, path traversal, SSTI
    2. **Authentication & Session** — weak tokens, missing auth checks, session fixation
    3. **Authorization** — IDOR, missing permission checks, privilege escalation
    4. **Secrets & Config** — hardcoded credentials, insecure defaults, env exposure
    5. **Cryptography** — weak algorithms, missing hashing, improper key management
    6. **Input Validation** — missing validation, mass assignment, schema exposure
    7. **Dependency Security** — obviously vulnerable packages
    8. **OWASP Top 10 Coverage** — check for each item
    9. **Data Privacy** — PII handling, logging sensitive data
    10. **Rate Limiting & DoS** — missing limits, unbounded loops

    For each issue:
    ## Security Issue #N [CRITICAL|HIGH|MEDIUM|LOW]: <Short title>
    **File**: <file_path>
    **OWASP Category**: <category>
    **Description**: <what and why it is vulnerable>
    **Exploit Scenario**: <how an attacker would exploit this>
    **Remediation**: <specific fix with code snippet if applicable>

    End with a security score (0–100) and executive summary.
""")

_FULL_CONTEXT_REVIEW_PROMPT = textwrap.dedent("""\
    You have access to the full codebase. Perform a holistic cross-file review looking for:

    1. **Cross-file Inconsistencies** — interface/implementation mismatches
    2. **Missing Integrations** — modules that reference but don't connect to each other
    3. **Global State Issues** — shared mutable state that could cause bugs
    4. **Architectural Drift** — code that deviates from the design document
    5. **Hidden Dependencies** — circular imports, implicit coupling
    6. **Configuration Gaps** — required env vars not documented
    7. **End-to-End Flow Coverage** — trace each user story through the code

    Format findings the same way as a code review (Issue #N [SEVERITY]).
""")


def _collect_code_files(project_dir: Path) -> dict[str, str]:
    """Read all source code files from the project artifacts."""
    code_dir = project_dir / "artifacts" / "code"
    files: dict[str, str] = {}
    for ext in ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.yaml", "*.yml", "*.toml"):
        for file_path in code_dir.rglob(ext):
            try:
                rel = str(file_path.relative_to(project_dir))
                files[rel] = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
    return files


def _format_codebase_for_prompt(files: dict[str, str], max_chars: int = 200_000) -> str:
    """Format collected files into a prompt string, truncating if needed."""
    parts: list[str] = []
    total = 0
    for rel_path, content in files.items():
        block = f"### FILE: {rel_path}\n```\n{content}\n```\n"
        if total + len(block) > max_chars:
            parts.append(f"### FILE: {rel_path}\n[TRUNCATED — file too large]\n")
        else:
            parts.append(block)
            total += len(block)
    return "\n".join(parts)


class Phase5ReviewExecutor:
    """Executes Phase 5 of the factory pipeline: cross-provider code and security review."""

    PHASE_NUMBER = 5
    PHASE_NAME = "cross_provider_review"

    async def execute(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        """Execute this phase. Returns result dict with artifacts produced."""
        logger.info("phase_5_started", run_id=str(run_id))
        result = await self._run(run_id, context)
        logger.info("phase_5_completed", run_id=str(run_id))
        return result

    async def _run(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        project_dir = Path(context.get("project_dir", ""))
        reviews_dir = project_dir / "artifacts" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)

        provider_registry = context.get("provider_registry")
        tier = context.get("tier", 2)
        model_assignments = context.get("model_assignments", {})

        # Collect code
        code_files = _collect_code_files(project_dir)
        codebase_text = _format_codebase_for_prompt(code_files)
        logger.info(
            "phase_5_codebase_collected",
            file_count=len(code_files),
            total_chars=len(codebase_text),
        )

        # ── Code Review ──────────────────────────────────────────────────
        code_review_content = await self._run_code_review(
            codebase_text=codebase_text,
            provider_registry=provider_registry,
            model_assignments=model_assignments,
            tier=tier,
        )
        code_review_path = reviews_dir / "code-review.md"
        code_review_path.write_text(code_review_content, encoding="utf-8")
        logger.info("code_review_written", path=str(code_review_path))

        # ── Security Audit ───────────────────────────────────────────────
        security_audit_content = await self._run_security_audit(
            codebase_text=codebase_text,
            provider_registry=provider_registry,
            model_assignments=model_assignments,
            tier=tier,
        )
        security_audit_path = reviews_dir / "security-audit.md"
        security_audit_path.write_text(security_audit_content, encoding="utf-8")
        logger.info("security_audit_written", path=str(security_audit_path))

        artifacts = {
            "code-review.md": str(code_review_path),
            "security-audit.md": str(security_audit_path),
        }

        # ── Tier 3: Full Context Review ──────────────────────────────────
        if tier >= 3:
            full_context_content = await self._run_full_context_review(
                codebase_text=codebase_text,
                provider_registry=provider_registry,
                model_assignments=model_assignments,
            )
            full_context_path = reviews_dir / "full-context-review.md"
            full_context_path.write_text(full_context_content, encoding="utf-8")
            artifacts["full-context-review.md"] = str(full_context_path)
            logger.info("full_context_review_written", path=str(full_context_path))

        # Count total issues from reviews
        total_issues = self._count_issues(code_review_content + security_audit_content)

        return {
            "phase": self.PHASE_NUMBER,
            "phase_name": self.PHASE_NAME,
            "status": "completed",
            "artifacts": artifacts,
            "total_issues_found": total_issues,
            "tier": tier,
        }

    async def _run_code_review(
        self,
        codebase_text: str,
        provider_registry: Any,
        model_assignments: dict,
        tier: int,
    ) -> str:
        """Run code review using the reviewer model (O3 or GPT per tier)."""
        reviewer_config = model_assignments.get(
            "code_reviewer",
            {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        )
        messages = [
            {"role": "system", "content": _CODE_REVIEW_PROMPT},
            {"role": "user", "content": f"Codebase to review:\n\n{codebase_text}"},
        ]
        return await self._call_provider(
            messages,
            provider_registry,
            preferred_provider=self._resolve_provider(reviewer_config),
            preferred_model=reviewer_config.get("model"),
            fallback_providers=["groq", "google_ai", "cerebras"],
        )

    async def _run_security_audit(
        self,
        codebase_text: str,
        provider_registry: Any,
        model_assignments: dict,
        tier: int,
    ) -> str:
        """Run security audit using a DIFFERENT provider from code review."""
        primary_config = model_assignments.get(
            "security_auditor",
            {"provider": "google_ai", "model": "gemini-2.0-flash"},
        )
        messages = [
            {"role": "system", "content": _SECURITY_AUDIT_PROMPT},
            {"role": "user", "content": f"Codebase to audit:\n\n{codebase_text}"},
        ]
        primary_result = await self._call_provider(
            messages,
            provider_registry,
            preferred_provider=self._resolve_provider(primary_config),
            preferred_model=primary_config.get("model"),
            fallback_providers=["sambanova", "groq", "cerebras"],
        )

        # Tier 3: second security audit from a different provider
        if tier >= 3:
            secondary_config = model_assignments.get(
                "security_auditor_secondary",
                {"provider": "sambanova", "model": "Meta-Llama-3.3-70B-Instruct"},
            )
            secondary_result = await self._call_provider(
                messages,
                provider_registry,
                preferred_provider=self._resolve_provider(secondary_config),
                preferred_model=secondary_config.get("model"),
                fallback_providers=["cerebras", "groq"],
            )
            return (
                "# Primary Security Audit\n\n"
                + primary_result
                + "\n\n---\n\n# Secondary Security Audit\n\n"
                + secondary_result
            )

        return primary_result

    async def _run_full_context_review(
        self,
        codebase_text: str,
        provider_registry: Any,
        model_assignments: dict,
    ) -> str:
        """Run full-context review (Tier 3 only), prefer large-context providers."""
        full_context_config = model_assignments.get(
            "full_context_review",
            {"provider": "google_ai", "model": "gemini-1.5-pro"},
        )
        messages = [
            {"role": "system", "content": _FULL_CONTEXT_REVIEW_PROMPT},
            {
                "role": "user",
                "content": f"Full codebase for holistic review:\n\n{codebase_text}",
            },
        ]
        return await self._call_provider(
            messages,
            provider_registry,
            preferred_provider=self._resolve_provider(full_context_config),
            preferred_model=full_context_config.get("model"),
            fallback_providers=["google_ai", "groq"],
        )

    async def _call_provider(
        self,
        messages: list[dict],
        provider_registry: Any,
        preferred_provider: str,
        preferred_model: str | None = None,
        fallback_providers: list[str] | None = None,
    ) -> str:
        if provider_registry is None:
            return "# Review\n\nNo provider available (stub output)."

        providers_to_try = [preferred_provider] + (fallback_providers or [])
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
                    temperature=0.1,
                    max_tokens=8192,
                    timeout=300.0,
                )
                logger.info(
                    "review_call_succeeded",
                    provider=provider_name,
                    model=model_obj.name,
                )
                return response.content
            except Exception as exc:
                logger.warning(
                    "review_call_failed",
                    provider=provider_name,
                    error=str(exc),
                )

        return "# Review\n\nAll providers failed. Manual review required."

    def _resolve_provider(self, config: dict) -> str:
        """Map model/via config to a registry provider name."""
        provider = config.get("provider", "")
        model = config.get("model", "")
        via = config.get("via", "")
        if provider:
            return provider
        if "gemini" in model:
            return "google_ai"
        if via in ("groq",):
            return "groq"
        return "groq"

    def _count_issues(self, review_text: str) -> int:
        """Count issue headings in review output."""
        import re
        return len(re.findall(r"^##\s+(?:Issue|Security Issue)\s+#\d+", review_text, re.MULTILINE))
