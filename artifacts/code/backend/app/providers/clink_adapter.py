"""Local CLI adapter routing through installed CLIs (claude, gemini, opencode, aider).

Model name format: "clink:<cli_name>" e.g. "clink:claude", "clink:gemini".
"""
from __future__ import annotations

import asyncio
import json
import shutil
import time
from datetime import datetime
from typing import AsyncIterator

import structlog

from app.providers.base import (
    CompletionResponse,
    HealthStatus,
    ModelInfo,
    RateLimitInfo,
)

logger = structlog.get_logger()

# Map CLI names to their invocation commands and metadata
_CLI_CATALOG: dict[str, dict] = {
    "claude": {
        "cmd": "claude",
        "display_name": "Claude (Local CLI)",
        "context_window": 200_000,
        "supports_tools": True,
        "supports_streaming": True,
        "capability_tags": ["local", "claude", "agentic"],
    },
    "gemini": {
        "cmd": "gemini",
        "display_name": "Gemini (Local CLI)",
        "context_window": 1_000_000,
        "supports_tools": True,
        "supports_streaming": True,
        "capability_tags": ["local", "gemini", "agentic"],
    },
    "opencode": {
        "cmd": "opencode",
        "display_name": "OpenCode (Local CLI)",
        "context_window": 128_000,
        "supports_tools": True,
        "supports_streaming": True,
        "capability_tags": ["local", "opencode", "coding"],
    },
    "aider": {
        "cmd": "aider",
        "display_name": "Aider (Local CLI)",
        "context_window": 128_000,
        "supports_tools": False,
        "supports_streaming": True,
        "capability_tags": ["local", "aider", "coding"],
    },
}

# Timeout for CLI subprocess calls
_DEFAULT_CLI_TIMEOUT = 300  # 5 minutes for agentic tasks


def _build_model_name(cli_name: str) -> str:
    return f"clink:{cli_name}"


def _parse_cli_name(model: str) -> str:
    """Extract cli_name from 'clink:<cli_name>' format."""
    if model.startswith("clink:"):
        return model[len("clink:"):]
    return model


def _messages_to_prompt(messages: list[dict]) -> str:
    """Flatten OpenAI-style messages into a single prompt string for CLI consumption."""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            parts.append(f"[System]: {content}")
        elif role == "assistant":
            parts.append(f"[Assistant]: {content}")
        else:
            parts.append(f"[User]: {content}")
    return "\n\n".join(parts)


class ClinkAdapter:
    """Provider adapter that invokes locally installed CLI tools."""

    name: str = "clink"
    display_name: str = "Local CLI (clink)"
    is_free: bool = True

    def __init__(self) -> None:
        self._available_clis: list[str] = self._discover_clis()
        logger.info("clink_adapter_init", available_clis=self._available_clis)

    def _discover_clis(self) -> list[str]:
        """Return list of CLI names that are found in PATH."""
        available: list[str] = []
        for cli_name, meta in _CLI_CATALOG.items():
            if shutil.which(meta["cmd"]) is not None:
                available.append(cli_name)
        return available

    # ── ProviderAdapter Protocol ──────────────────────────────────────────────

    async def list_models(self) -> list[ModelInfo]:
        """Return ModelInfo entries for each available local CLI."""
        models: list[ModelInfo] = []
        for cli_name in self._available_clis:
            meta = _CLI_CATALOG[cli_name]
            models.append(
                ModelInfo(
                    name=_build_model_name(cli_name),
                    display_name=meta["display_name"],
                    provider=self.name,
                    context_window=meta["context_window"],
                    supports_tools=meta.get("supports_tools", False),
                    supports_streaming=meta.get("supports_streaming", False),
                    supports_vision=False,
                    is_free=True,
                    cost_per_1k_input=0.0,
                    cost_per_1k_output=0.0,
                    capability_tags=meta.get("capability_tags", []),
                )
            )
        return models

    async def chat_completion(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        tools: list[dict] | None = None,
        timeout: float = _DEFAULT_CLI_TIMEOUT,
    ) -> CompletionResponse:
        """Execute a request via the local CLI and capture stdout as the response."""
        cli_name = _parse_cli_name(model)
        meta = _CLI_CATALOG.get(cli_name)
        if not meta:
            raise ValueError(f"Unknown clink CLI: '{cli_name}'. Available: {list(_CLI_CATALOG)}")
        if cli_name not in self._available_clis:
            raise RuntimeError(f"CLI '{cli_name}' (cmd: {meta['cmd']}) not found in PATH")

        prompt = _messages_to_prompt(messages)
        cmd = self._build_command(cli_name, prompt, max_tokens)

        start_ms = int(time.monotonic() * 1000)
        try:
            stdout, stderr_text = await self._run_subprocess(cmd, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"CLI '{cli_name}' timed out after {timeout}s")

        latency_ms = int(time.monotonic() * 1000) - start_ms

        if not stdout and stderr_text:
            logger.warning("clink_cli_stderr", cli=cli_name, stderr=stderr_text[:500])

        # Attempt to parse JSON response, fall back to raw text
        content = self._parse_output(cli_name, stdout)
        tokens_output = max(1, len(content.split()))

        return CompletionResponse(
            content=content,
            model=model,
            provider=self.name,
            tokens_input=max(1, len(prompt.split())),
            tokens_output=tokens_output,
            cost=0.0,
            latency_ms=latency_ms,
            finish_reason="stop",
            tool_calls=None,
            raw_response={"stdout": stdout[:2000], "stderr": stderr_text[:500]},
        )

    async def stream_completion(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = _DEFAULT_CLI_TIMEOUT,
    ) -> AsyncIterator[str]:
        """Stream output from the CLI line by line."""
        cli_name = _parse_cli_name(model)
        meta = _CLI_CATALOG.get(cli_name)
        if not meta:
            raise ValueError(f"Unknown clink CLI: '{cli_name}'")

        prompt = _messages_to_prompt(messages)
        cmd = self._build_command(cli_name, prompt, max_tokens)

        return _stream_cli_output(cmd, timeout)

    async def check_health(self) -> HealthStatus:
        """Check that at least one CLI is available."""
        start_ms = int(time.monotonic() * 1000)
        if self._available_clis:
            # Re-run discovery in case environment changed
            self._available_clis = self._discover_clis()
            latency_ms = int(time.monotonic() * 1000) - start_ms
            return HealthStatus(
                is_healthy=bool(self._available_clis),
                latency_ms=latency_ms,
                error=None if self._available_clis else "No local CLIs found in PATH",
                last_checked=datetime.utcnow(),
            )
        latency_ms = int(time.monotonic() * 1000) - start_ms
        return HealthStatus(
            is_healthy=False,
            latency_ms=latency_ms,
            error="No local CLIs (claude/gemini/opencode/aider) found in PATH",
            last_checked=datetime.utcnow(),
        )

    async def get_rate_limits(self) -> RateLimitInfo:
        """Local CLIs are not rate-limited."""
        return RateLimitInfo(
            rpm_limit=0,
            rpd_limit=0,
            rpm_remaining=0,
            rpd_remaining=0,
            tpm_limit=0,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_command(
        self, cli_name: str, prompt: str, max_tokens: int | None
    ) -> list[str]:
        """Build the subprocess command list for the given CLI."""
        meta = _CLI_CATALOG[cli_name]
        cmd_name = meta["cmd"]

        if cli_name == "claude":
            # claude CLI: read from stdin with --print flag for non-interactive output
            return [cmd_name, "--print", "--dangerously-skip-permissions", "-"]
        elif cli_name == "gemini":
            return [cmd_name, "-p", prompt]
        elif cli_name == "opencode":
            return [cmd_name, "run", "--prompt", prompt]
        elif cli_name == "aider":
            # aider reads prompt from stdin in non-interactive mode
            return [cmd_name, "--yes", "--no-pretty", "--message", prompt]
        else:
            return [cmd_name, prompt]

    async def _run_subprocess(
        self, cmd: list[str], timeout: float
    ) -> tuple[str, str]:
        """Run a subprocess and return (stdout, stderr) as strings."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise

        return stdout_bytes.decode("utf-8", errors="replace"), stderr_bytes.decode(
            "utf-8", errors="replace"
        )

    def _parse_output(self, cli_name: str, raw: str) -> str:
        """Parse CLI stdout into a clean content string."""
        # Some CLIs may output JSON; try to extract "content" or "response" field
        stripped = raw.strip()
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
                for key in ("content", "response", "text", "output", "result"):
                    if key in data:
                        return str(data[key])
            except json.JSONDecodeError:
                pass
        return stripped


async def _stream_cli_output(cmd: list[str], timeout: float) -> AsyncIterator[str]:
    """Async generator that yields stdout lines from a CLI subprocess."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert proc.stdout is not None

    try:
        async for line in proc.stdout:
            yield line.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        proc.kill()
        raise
    finally:
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
