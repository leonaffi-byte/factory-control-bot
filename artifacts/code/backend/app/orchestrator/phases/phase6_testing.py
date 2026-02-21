"""Phase 6: Test Execution and Fix Cycle implementation.

Runs tests against the implementation, passes only failure messages to the
implementer (not test code), and iterates up to max_fix_cycles (default 5).
Also applies fixes for issues found in Phase 5 reviews.
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger()

MAX_FIX_CYCLES = 5
_ESCALATE_AFTER_SAME_FAILURE = 3

_FIX_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a backend engineer fixing failing tests.

    IMPORTANT: You will only receive the test FAILURE OUTPUT, not the test code.
    You have access to the implementation code only.

    Rules:
    - Read the failure message carefully to understand what the production code is doing wrong
    - Fix ONLY the implementation code — never modify the test expectations
    - Make the smallest correct change to fix the issue
    - Do not introduce new bugs while fixing
    - If a fix requires changing an interface, note it clearly

    Output only the fixed file(s) in this format:
    ### FILE: <relative_path>
    ```python
    <full corrected file content>
    ```
""")

_REVIEW_FIX_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a backend engineer fixing issues found in a code review.
    You will receive a list of issues from the review and the relevant source files.

    For each CRITICAL or HIGH severity issue:
    - Provide the corrected file content
    - Explain the change briefly above the code block

    For MEDIUM/LOW issues, provide fixes if straightforward.

    Output format:
    ### FIX: Issue #N — <short title>
    Explanation: <one line>

    ### FILE: <relative_path>
    ```python
    <full corrected file content>
    ```
""")


async def _run_tests(tests_dir: Path, code_dir: Path, timeout: int = 120) -> tuple[bool, str]:
    """Run pytest and return (passed, output_text)."""
    if not tests_dir.exists() or not any(tests_dir.rglob("test_*.py")):
        logger.warning("no_test_files_found", tests_dir=str(tests_dir))
        return True, "No test files found — skipping test execution."

    cmd = [
        "python", "-m", "pytest",
        str(tests_dir),
        "-v",
        "--tb=short",
        "--no-header",
        "-q",
    ]

    env = {
        "PYTHONPATH": str(code_dir / "backend"),
    }

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                cwd=str(code_dir / "backend"),
                env={**__import__("os").environ, **env},
                timeout=timeout,
            ),
            timeout=timeout + 10,
        )
        passed = result.returncode == 0
        output = result.stdout + result.stderr
        return passed, output
    except asyncio.TimeoutError:
        return False, f"Test run timed out after {timeout}s"
    except Exception as exc:
        return False, f"Test runner error: {exc}"


def _parse_review_issues(review_text: str) -> list[dict]:
    """Extract issues from code-review.md and security-audit.md."""
    issues: list[dict] = []
    pattern = re.compile(
        r"##\s+(?:Issue|Security Issue)\s+#(\d+)\s+\[(CRITICAL|HIGH|MEDIUM|LOW)\]:\s*(.+)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(review_text):
        issues.append({
            "number": int(match.group(1)),
            "severity": match.group(2).upper(),
            "title": match.group(3).strip(),
        })
    return issues


def _read_review_files(reviews_dir: Path) -> str:
    """Read all review files and return combined text."""
    combined: list[str] = []
    for review_file in ("code-review.md", "security-audit.md", "full-context-review.md"):
        path = reviews_dir / review_file
        if path.exists():
            combined.append(f"# {review_file}\n\n{path.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(combined)


def _collect_implementation_code(code_dir: Path, max_chars: int = 100_000) -> str:
    """Read backend implementation files for the fix prompt."""
    backend_dir = code_dir / "backend"
    parts: list[str] = []
    total = 0
    for py_file in sorted(backend_dir.rglob("*.py")):
        try:
            rel = str(py_file.relative_to(code_dir))
            content = py_file.read_text(encoding="utf-8", errors="replace")
            block = f"### FILE: {rel}\n```python\n{content}\n```\n"
            if total + len(block) < max_chars:
                parts.append(block)
                total += len(block)
        except Exception:
            pass
    return "\n".join(parts)


def _parse_file_blocks(llm_output: str) -> dict[str, str]:
    """Parse ### FILE: <path> code blocks from LLM output."""
    files: dict[str, str] = {}
    pattern = re.compile(
        r"###\s+FILE:\s+(?P<path>[^\n]+)\n```[^\n]*\n(?P<content>.*?)```",
        re.DOTALL,
    )
    for match in pattern.finditer(llm_output):
        files[match.group("path").strip()] = match.group("content")
    return files


def _write_fixed_files(code_dir: Path, fixed_files: dict[str, str]) -> list[str]:
    """Apply fixed files to the implementation directory."""
    written: list[str] = []
    for rel_path, content in fixed_files.items():
        # Security: only allow writes inside artifacts/code/
        safe_path = code_dir / rel_path
        if not str(safe_path.resolve()).startswith(str(code_dir.resolve())):
            logger.warning("fix_path_traversal_blocked", path=rel_path)
            continue
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")
        written.append(str(safe_path))
    return written


class Phase6TestingExecutor:
    """Executes Phase 6 of the factory pipeline: test execution and fix cycles."""

    PHASE_NUMBER = 6
    PHASE_NAME = "test_execution_and_fix_cycle"

    async def execute(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        """Execute this phase. Returns result dict with artifacts produced."""
        logger.info("phase_6_started", run_id=str(run_id))
        result = await self._run(run_id, context)
        logger.info("phase_6_completed", run_id=str(run_id))
        return result

    async def _run(self, run_id: "UUID", context: dict[str, Any]) -> dict[str, Any]:
        project_dir = Path(context.get("project_dir", ""))
        code_dir = project_dir / "artifacts" / "code"
        tests_dir = project_dir / "artifacts" / "tests"
        reviews_dir = project_dir / "artifacts" / "reviews"

        provider_registry = context.get("provider_registry")
        tier = context.get("tier", 2)
        max_fix_cycles = context.get("max_fix_cycles", MAX_FIX_CYCLES)

        fix_cycle = 0
        consecutive_same_failures = 0
        last_failure_hash: str | None = None
        all_cycles: list[dict] = []

        # Step 1: Apply review fixes first (before running tests)
        if reviews_dir.exists():
            review_text = _read_review_files(reviews_dir)
            review_issues = _parse_review_issues(review_text)
            critical_high = [
                i for i in review_issues if i["severity"] in ("CRITICAL", "HIGH")
            ]
            if critical_high:
                logger.info(
                    "phase_6_applying_review_fixes",
                    critical_high_count=len(critical_high),
                )
                await self._apply_review_fixes(
                    review_text=review_text,
                    code_dir=code_dir,
                    provider_registry=provider_registry,
                )

        # Step 2: Test-fix cycle
        for cycle_num in range(1, max_fix_cycles + 1):
            logger.info(
                "phase_6_test_cycle",
                run_id=str(run_id),
                cycle=cycle_num,
                max_cycles=max_fix_cycles,
            )

            passed, output = await _run_tests(tests_dir, code_dir)
            cycle_record = {
                "cycle": cycle_num,
                "passed": passed,
                "output_summary": output[:2000],
            }
            all_cycles.append(cycle_record)

            if passed:
                logger.info(
                    "phase_6_tests_passed",
                    run_id=str(run_id),
                    cycle=cycle_num,
                )
                return {
                    "phase": self.PHASE_NUMBER,
                    "phase_name": self.PHASE_NAME,
                    "status": "completed",
                    "tests_passed": True,
                    "fix_cycles": cycle_num - 1,
                    "cycles": all_cycles,
                    "tier": tier,
                }

            # Tests failed — check for repeated identical failure
            failure_hash = str(hash(output[:500]))
            if failure_hash == last_failure_hash:
                consecutive_same_failures += 1
            else:
                consecutive_same_failures = 1
                last_failure_hash = failure_hash

            if consecutive_same_failures >= _ESCALATE_AFTER_SAME_FAILURE:
                logger.warning(
                    "phase_6_escalating_same_failure",
                    run_id=str(run_id),
                    cycle=cycle_num,
                    consecutive=consecutive_same_failures,
                )
                return {
                    "phase": self.PHASE_NUMBER,
                    "phase_name": self.PHASE_NAME,
                    "status": "escalated",
                    "tests_passed": False,
                    "fix_cycles": cycle_num,
                    "cycles": all_cycles,
                    "escalation_reason": f"Same failure repeated {consecutive_same_failures} times",
                    "tier": tier,
                }

            fix_cycle += 1
            logger.info(
                "phase_6_fix_cycle_start",
                run_id=str(run_id),
                fix_cycle=fix_cycle,
            )

            # Send ONLY failure output to implementer (information barrier)
            fixed_files = await self._request_fix(
                failure_output=output,
                code_dir=code_dir,
                provider_registry=provider_registry,
            )
            if fixed_files:
                written = _write_fixed_files(code_dir, fixed_files)
                logger.info(
                    "phase_6_fix_applied",
                    run_id=str(run_id),
                    fix_cycle=fix_cycle,
                    files_fixed=len(written),
                )
            else:
                logger.warning(
                    "phase_6_no_fix_produced",
                    run_id=str(run_id),
                    fix_cycle=fix_cycle,
                )

        # Exhausted all fix cycles
        logger.error(
            "phase_6_max_fix_cycles_reached",
            run_id=str(run_id),
            max_cycles=max_fix_cycles,
        )
        return {
            "phase": self.PHASE_NUMBER,
            "phase_name": self.PHASE_NAME,
            "status": "failed",
            "tests_passed": False,
            "fix_cycles": max_fix_cycles,
            "cycles": all_cycles,
            "tier": tier,
        }

    async def _request_fix(
        self,
        failure_output: str,
        code_dir: Path,
        provider_registry: Any,
    ) -> dict[str, str]:
        """Ask an LLM to fix the implementation based on failure output only."""
        if provider_registry is None:
            logger.warning("no_provider_for_fix")
            return {}

        implementation_code = _collect_implementation_code(code_dir)

        # INFORMATION BARRIER: send failure OUTPUT only, never test source code
        messages = [
            {"role": "system", "content": _FIX_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "## Test Failure Output\n\n"
                    f"```\n{failure_output[:8000]}\n```\n\n"
                    "## Implementation Code\n\n"
                    f"{implementation_code}"
                ),
            },
        ]

        for provider_name in ("google_ai", "groq", "cerebras", "sambanova"):
            if provider_name not in provider_registry:
                continue
            try:
                adapter = provider_registry.get_provider(provider_name)
                models = await adapter.list_models()
                if not models:
                    continue
                model = sorted(models, key=lambda m: m.context_window, reverse=True)[0]
                response = await adapter.chat_completion(
                    model=model.name,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=8192,
                    timeout=300.0,
                )
                return _parse_file_blocks(response.content)
            except Exception as exc:
                logger.warning("fix_call_failed", provider=provider_name, error=str(exc))

        return {}

    async def _apply_review_fixes(
        self,
        review_text: str,
        code_dir: Path,
        provider_registry: Any,
    ) -> None:
        """Apply fixes for CRITICAL/HIGH issues from review phase."""
        if provider_registry is None:
            return

        implementation_code = _collect_implementation_code(code_dir)

        messages = [
            {"role": "system", "content": _REVIEW_FIX_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "## Code Review Issues\n\n"
                    f"{review_text[:8000]}\n\n"
                    "## Implementation Code\n\n"
                    f"{implementation_code}"
                ),
            },
        ]

        for provider_name in ("google_ai", "groq", "cerebras", "sambanova"):
            if provider_name not in provider_registry:
                continue
            try:
                adapter = provider_registry.get_provider(provider_name)
                models = await adapter.list_models()
                if not models:
                    continue
                model = sorted(models, key=lambda m: m.context_window, reverse=True)[0]
                response = await adapter.chat_completion(
                    model=model.name,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=8192,
                    timeout=300.0,
                )
                fixed_files = _parse_file_blocks(response.content)
                if fixed_files:
                    written = _write_fixed_files(code_dir, fixed_files)
                    logger.info(
                        "review_fixes_applied",
                        files_fixed=len(written),
                        provider=provider_name,
                    )
                return
            except Exception as exc:
                logger.warning("review_fix_call_failed", provider=provider_name, error=str(exc))
