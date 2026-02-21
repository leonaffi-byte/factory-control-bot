"""AI engine CLI installation step."""

from __future__ import annotations

import asyncio
import shutil

import structlog

logger = structlog.get_logger()

# Install commands for each AI engine CLI
ENGINE_INSTALL_COMMANDS: dict[str, list[str]] = {
    "claude": ["npm", "install", "-g", "@anthropic-ai/claude-code"],
    "gemini": ["npm", "install", "-g", "@google/gemini-cli"],
    "opencode": ["go", "install", "github.com/opencode-ai/opencode@latest"],
    "aider": ["pip", "install", "aider-chat"],
}

# Binary names to check for existence
ENGINE_BINARIES: dict[str, str] = {
    "claude": "claude",
    "gemini": "gemini",
    "opencode": "opencode",
    "aider": "aider",
}


async def check_engine(engine: str) -> bool:
    """
    Check whether the given AI engine CLI is installed and callable.

    Args:
        engine: Engine name, one of "claude", "gemini", "opencode", "aider".

    Returns:
        True if the binary is found on PATH.
    """
    binary = ENGINE_BINARIES.get(engine)
    if binary is None:
        logger.warning("unknown_engine_check", engine=engine)
        return False
    return shutil.which(binary) is not None


async def install_engine(engine: str) -> bool:
    """
    Install the CLI for a single AI engine.

    Args:
        engine: Engine name, one of the keys in ENGINE_INSTALL_COMMANDS.

    Returns:
        True if already installed or installation succeeded.
    """
    if await check_engine(engine):
        logger.info("engine_already_installed", engine=engine)
        return True

    cmd = ENGINE_INSTALL_COMMANDS.get(engine)
    if cmd is None:
        logger.warning("unknown_engine_install", engine=engine)
        return False

    # Check that the installer binary is available
    installer = cmd[0]
    if shutil.which(installer) is None:
        logger.error(
            "engine_installer_not_found",
            engine=engine,
            installer=installer,
        )
        return False

    logger.info("installing_engine", engine=engine, command=cmd)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("engine_installed", engine=engine)
            return True
        logger.error(
            "engine_install_failed",
            engine=engine,
            returncode=proc.returncode,
            stderr=stderr.decode(errors="replace")[:500],
        )
        return False
    except OSError as e:
        logger.error("engine_install_error", engine=engine, error=str(e))
        return False


async def install_all_engines() -> dict[str, bool]:
    """
    Attempt to install all known AI engine CLIs in parallel.

    Returns:
        Dict mapping engine name -> True (success) / False (failure).
    """
    engines = list(ENGINE_INSTALL_COMMANDS.keys())
    results_list = await asyncio.gather(
        *[install_engine(e) for e in engines],
        return_exceptions=False,
    )
    results = dict(zip(engines, results_list))
    logger.info("all_engines_install_complete", results=results)
    return results
