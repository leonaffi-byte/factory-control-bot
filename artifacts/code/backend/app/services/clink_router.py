"""Clink router — routes prompts through locally installed CLI AI engines."""

from __future__ import annotations

import asyncio
import shutil
from typing import ClassVar

import structlog

logger = structlog.get_logger()

# Known CLI engines and their executable names
_ENGINE_EXECUTABLES: dict[str, str] = {
    "claude": "claude",
    "gemini": "gemini",
    "opencode": "opencode",
    "aider": "aider",
}

# Prompt delivery strategy per engine
# "stdin"  -> write prompt to stdin
# "arg"    -> pass prompt as a command-line argument (e.g. gemini -p "...")
_ENGINE_PROMPT_MODE: dict[str, str] = {
    "claude": "stdin",
    "gemini": "arg",
    "opencode": "stdin",
    "aider": "stdin",
}

# Extra flags per engine for non-interactive single-shot usage
_ENGINE_FLAGS: dict[str, list[str]] = {
    "claude": ["--print"],
    "gemini": ["-p"],
    "opencode": [],
    "aider": ["--yes", "--message"],
}


class ClinkRouterError(Exception):
    """Raised when a clink routing operation fails."""


class ClinkRouter:
    """
    Routes prompts through local CLI AI engine installations.

    Supported engines: claude, gemini, opencode, aider.
    Uses shutil.which() to detect installed engines; no API keys required.
    """

    # Class-level cache so repeated calls don't re-probe the filesystem
    _available_cache: ClassVar[dict[str, bool] | None] = None

    async def list_available_engines(self) -> list[str]:
        """
        Return a list of engine names whose CLI executables are installed.

        Results are cached for the lifetime of the process.
        """
        if ClinkRouter._available_cache is None:
            results: dict[str, bool] = {}
            for engine in _ENGINE_EXECUTABLES:
                results[engine] = await self.check_engine_installed(engine)
            ClinkRouter._available_cache = results
            logger.info(
                "clink_engines_discovered",
                available=[e for e, ok in results.items() if ok],
            )

        return [e for e, ok in ClinkRouter._available_cache.items() if ok]

    async def check_engine_installed(self, engine: str) -> bool:
        """
        Check whether *engine*'s CLI executable is available on PATH.

        Args:
            engine: Engine key (e.g. "claude", "gemini").

        Returns:
            True if the executable exists and is executable, False otherwise.
        """
        executable = _ENGINE_EXECUTABLES.get(engine)
        if not executable:
            return False
        # shutil.which is synchronous but fast; run in thread to be safe
        path = await asyncio.to_thread(shutil.which, executable)
        found = path is not None
        logger.debug("engine_check", engine=engine, executable=executable, found=found)
        return found

    async def route_to_engine(self, engine: str, prompt: str) -> str:
        """
        Send *prompt* to *engine* and return the captured stdout response.

        Args:
            engine: Engine key (e.g. "claude", "aider").
            prompt: The prompt text to send.

        Returns:
            Raw stdout string from the engine.

        Raises:
            ClinkRouterError: If the engine is not installed, returns non-zero,
                              or produces no output.
        """
        if not await self.check_engine_installed(engine):
            raise ClinkRouterError(
                f"Engine '{engine}' is not installed or not found on PATH."
            )

        executable = _ENGINE_EXECUTABLES[engine]
        flags = _ENGINE_FLAGS.get(engine, [])
        prompt_mode = _ENGINE_PROMPT_MODE.get(engine, "stdin")

        if prompt_mode == "arg":
            # e.g. gemini -p "prompt text"
            cmd = [executable] + flags + [prompt]
            stdin_data: bytes | None = None
        else:
            # e.g. claude --print  < stdin
            cmd = [executable] + flags
            stdin_data = prompt.encode("utf-8")

        logger.info(
            "clink_routing",
            engine=engine,
            cmd=cmd,
            prompt_mode=prompt_mode,
            prompt_length=len(prompt),
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=300.0,  # 5 minutes max
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise ClinkRouterError(
                f"Engine '{engine}' timed out after 300 seconds."
            )
        except Exception as exc:
            raise ClinkRouterError(
                f"Failed to launch engine '{engine}': {exc}"
            ) from exc

        if proc.returncode != 0:
            err_text = stderr.decode(errors="replace").strip()
            raise ClinkRouterError(
                f"Engine '{engine}' exited with code {proc.returncode}. "
                f"Stderr: {err_text[:500]}"
            )

        output = stdout.decode(errors="replace").strip()
        if not output:
            raise ClinkRouterError(
                f"Engine '{engine}' returned empty output."
            )

        logger.info(
            "clink_response_received",
            engine=engine,
            output_length=len(output),
        )
        return output
