"""PostgreSQL installation step."""

from __future__ import annotations

import asyncio
import shutil

import structlog

logger = structlog.get_logger()


async def check_postgres_running() -> bool:
    """
    Check whether PostgreSQL is currently running and accepting connections.

    Returns:
        True if pg_isready exits with code 0.
    """
    if shutil.which("pg_isready") is None:
        logger.debug("pg_isready_not_found")
        return False

    try:
        proc = await asyncio.create_subprocess_exec(
            "pg_isready",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0
    except OSError as e:
        logger.warning("check_postgres_running_error", error=str(e))
        return False


async def install_postgres() -> bool:
    """
    Install PostgreSQL using the system package manager.

    Supports: apt (Ubuntu/Debian), brew (macOS), dnf (Fedora).

    Returns:
        True if installation succeeded.
    """
    if shutil.which("apt-get"):
        cmd = ["apt-get", "install", "-y", "postgresql", "postgresql-client"]
    elif shutil.which("brew"):
        cmd = ["brew", "install", "postgresql@15"]
    elif shutil.which("dnf"):
        cmd = ["dnf", "install", "-y", "postgresql-server", "postgresql"]
    else:
        logger.error("no_supported_package_manager_for_postgres")
        return False

    logger.info("installing_postgres", command=cmd)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("postgres_installed")
            return True
        logger.error(
            "postgres_install_failed",
            returncode=proc.returncode,
            stderr=stderr.decode(errors="replace")[:500],
        )
        return False
    except OSError as e:
        logger.error("postgres_install_error", error=str(e))
        return False


async def create_database(db_name: str, db_user: str, db_pass: str) -> bool:
    """
    Create a PostgreSQL database and user.

    Runs the SQL as the 'postgres' superuser via psql.

    Args:
        db_name: Name of the database to create.
        db_user: Database user to create.
        db_pass: Password for the new user.

    Returns:
        True if both the user and database were created successfully.
    """
    if shutil.which("psql") is None:
        logger.error("psql_not_found")
        return False

    sql = (
        f"DO $$ BEGIN "
        f"  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{db_user}') THEN "
        f"    CREATE ROLE \"{db_user}\" WITH LOGIN PASSWORD '{db_pass}'; "
        f"  END IF; "
        f"END $$; "
        f"SELECT 'CREATE DATABASE' WHERE NOT EXISTS "
        f"  (SELECT FROM pg_database WHERE datname = '{db_name}') "
        f"\\gexec "
        f"GRANT ALL PRIVILEGES ON DATABASE \"{db_name}\" TO \"{db_user}\";"
    )

    logger.info("creating_database", db_name=db_name, db_user=db_user)
    try:
        proc = await asyncio.create_subprocess_exec(
            "psql",
            "-U", "postgres",
            "-c", sql,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("database_created", db_name=db_name)
            return True
        logger.error(
            "database_create_failed",
            returncode=proc.returncode,
            stderr=stderr.decode(errors="replace")[:500],
        )
        return False
    except OSError as e:
        logger.error("database_create_error", error=str(e))
        return False
