"""Backup service — database and project backup/restore with retention policy."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.models.backup import Backup

if TYPE_CHECKING:
    from app.database.session import AsyncSessionFactory

logger = structlog.get_logger()

# ── DTOs ────────────────────────────────────────────────────────────────────


@dataclass
class RestoreResult:
    success: bool
    backup_id: int
    schema_compatible: bool = False
    safety_snapshot_path: str | None = None
    error: str | None = None
    warnings: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


# ── Retention policy constants ───────────────────────────────────────────────

_RETENTION_DAILY = 7     # keep 7 most-recent daily backups
_RETENTION_WEEKLY = 4    # keep 4 most-recent weekly backups
_RETENTION_MONTHLY = 3   # keep 3 most-recent monthly backups


class BackupService:
    """
    Creates, restores, lists, and applies retention policy to database backups.

    Backups are created via pg_dump and stored as .sql.gz files in
    settings.backup_dir.  Metadata is persisted in the `backups` table.
    """

    def __init__(self, session_factory: "AsyncSessionFactory") -> None:
        self._session_factory = session_factory

    async def create_backup(self, backup_type: str = "manual") -> Backup:
        """
        Dump the PostgreSQL database to a compressed file and record it.

        Args:
            backup_type: One of "manual" | "daily" | "weekly" | "monthly".

        Returns:
            Persisted Backup ORM record.

        Raises:
            RuntimeError: If the pg_dump command fails.
        """
        from app.config import get_settings
        settings = get_settings()

        backup_dir = Path(settings.backup_dir)
        await asyncio.to_thread(backup_dir.mkdir, parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"factory_backup_{backup_type}_{timestamp}.sql.gz"
        file_path = backup_dir / filename

        # Determine retention date
        retention_until = self._retention_date(backup_type)

        # Run pg_dump
        db_url = settings.database_url
        try:
            await asyncio.to_thread(
                self._run_pg_dump,
                db_url=db_url,
                output_path=file_path,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"pg_dump failed: {exc.stderr}") from exc

        # Compute checksum
        checksum = await asyncio.to_thread(self._sha256, file_path)
        file_size = file_path.stat().st_size

        # Determine schema version (use alembic if available)
        schema_version = await self._get_schema_version()

        async with self._session_factory() as session:
            backup = Backup(
                backup_type=backup_type,
                file_path=str(file_path),
                file_size_bytes=file_size,
                sha256_checksum=checksum,
                schema_version=schema_version,
                includes_db=True,
                includes_projects=False,
                includes_config=False,
                retention_until=retention_until,
                status="completed",
            )
            session.add(backup)
            await session.flush()
            await session.refresh(backup)

        logger.info(
            "backup_created",
            backup_id=backup.id,
            backup_type=backup_type,
            file_path=str(file_path),
            size_bytes=file_size,
            checksum=checksum,
        )
        return backup

    async def restore_backup(
        self, backup_id: int, passphrase: str = ""
    ) -> RestoreResult:
        """
        Restore the database from a previously created backup.

        Safety steps:
        1. Create a safety snapshot of the current database.
        2. Verify the backup file exists and checksum matches.
        3. Restore via psql.

        Args:
            backup_id: Primary key of the Backup record to restore.
            passphrase: Reserved for future encrypted backup support.

        Returns:
            RestoreResult with success flag and safety snapshot path.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(Backup).where(Backup.id == backup_id)
            )
            backup: Backup | None = result.scalar_one_or_none()

        if backup is None:
            return RestoreResult(
                success=False,
                backup_id=backup_id,
                error=f"Backup {backup_id} not found",
            )

        file_path = Path(backup.file_path)
        if not file_path.exists():
            return RestoreResult(
                success=False,
                backup_id=backup_id,
                error=f"Backup file not found: {file_path}",
            )

        warnings: list[str] = []

        # Verify checksum
        actual_checksum = await asyncio.to_thread(self._sha256, file_path)
        if actual_checksum != backup.sha256_checksum:
            return RestoreResult(
                success=False,
                backup_id=backup_id,
                error=(
                    f"Checksum mismatch: expected {backup.sha256_checksum}, "
                    f"got {actual_checksum}"
                ),
            )

        # Safety snapshot
        safety_snapshot: str | None = None
        try:
            safety_backup = await self.create_backup(backup_type="safety_snapshot")
            safety_snapshot = safety_backup.file_path
        except Exception as exc:
            warnings.append(f"Safety snapshot failed: {exc}")

        # Determine schema compatibility
        current_version = await self._get_schema_version()
        schema_compatible = current_version == backup.schema_version
        if not schema_compatible:
            warnings.append(
                f"Schema version mismatch: current={current_version}, "
                f"backup={backup.schema_version}. Migration may be needed."
            )

        from app.config import get_settings
        settings = get_settings()

        try:
            await asyncio.to_thread(
                self._run_pg_restore,
                db_url=settings.database_url,
                input_path=file_path,
            )
        except subprocess.CalledProcessError as exc:
            return RestoreResult(
                success=False,
                backup_id=backup_id,
                schema_compatible=schema_compatible,
                safety_snapshot_path=safety_snapshot,
                error=f"pg restore failed: {exc.stderr}",
                warnings=warnings,
            )

        logger.info(
            "backup_restored",
            backup_id=backup_id,
            schema_compatible=schema_compatible,
            safety_snapshot=safety_snapshot,
        )
        return RestoreResult(
            success=True,
            backup_id=backup_id,
            schema_compatible=schema_compatible,
            safety_snapshot_path=safety_snapshot,
            warnings=warnings,
        )

    async def list_backups(self) -> list[Backup]:
        """Return all Backup records ordered by most recent first."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Backup).order_by(Backup.created_at.desc())
            )
            return list(result.scalars().all())

    async def apply_retention_policy(self) -> int:
        """
        Delete backup files and database records that have exceeded their
        retention dates or are beyond the configured keep counts.

        Retention rules:
            daily   -> keep 7
            weekly  -> keep 4
            monthly -> keep 3

        Returns:
            Number of backups deleted.
        """
        deleted = 0
        async with self._session_factory() as session:
            for backup_type, keep_count in [
                ("daily", _RETENTION_DAILY),
                ("weekly", _RETENTION_WEEKLY),
                ("monthly", _RETENTION_MONTHLY),
            ]:
                result = await session.execute(
                    select(Backup)
                    .where(Backup.backup_type == backup_type)
                    .order_by(Backup.created_at.desc())
                )
                backups: list[Backup] = list(result.scalars().all())
                to_delete = backups[keep_count:]

                for b in to_delete:
                    try:
                        path = Path(b.file_path)
                        if path.exists():
                            await asyncio.to_thread(path.unlink)
                        await session.delete(b)
                        deleted += 1
                    except Exception as exc:
                        logger.warning(
                            "backup_delete_failed",
                            backup_id=b.id,
                            error=str(exc),
                        )

        logger.info("retention_policy_applied", deleted=deleted)
        return deleted

    # ── Private helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _retention_date(backup_type: str) -> date | None:
        today = date.today()
        if backup_type == "daily":
            return today + timedelta(days=_RETENTION_DAILY)
        if backup_type == "weekly":
            return today + timedelta(weeks=_RETENTION_WEEKLY)
        if backup_type == "monthly":
            return today + timedelta(days=30 * _RETENTION_MONTHLY)
        return None

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _parse_db_url(db_url: str) -> tuple[str, str, str, str, str]:
        """Parse a SQLAlchemy database URL into (user, password, host, port, dbname).

        Uses urllib.parse so that percent-encoded characters (e.g. special chars
        in passwords) are handled correctly, and never crashes on edge-case URLs
        that defeat naive regex patterns.
        """
        import os
        from urllib.parse import unquote, urlparse

        parsed = urlparse(db_url)
        user = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        host = parsed.hostname or "localhost"
        port = str(parsed.port or 5432)
        dbname = parsed.path.lstrip("/")
        if not user or not dbname:
            raise ValueError(f"Cannot parse database URL: {db_url!r}")
        return user, password, host, port, dbname

    @staticmethod
    def _run_pg_dump(db_url: str, output_path: Path) -> None:
        """Run pg_dump and gzip the output."""
        import os

        user, password, host, port, dbname = BackupService._parse_db_url(db_url)

        # Merge PGPASSWORD into the *existing* process environment so that
        # other variables required by pg_dump (e.g. PATH, LD_LIBRARY_PATH)
        # are preserved.  Replacing env entirely can break pg_dump on some
        # systems where the binary is not on /usr/bin.
        env = {**os.environ, "PGPASSWORD": password}

        cmd = [
            "pg_dump",
            "-h", host,
            "-p", port,
            "-U", user,
            "-d", dbname,
            "-F", "p",   # plain text
        ]
        with open(output_path, "wb") as out:
            dump = subprocess.run(
                cmd, env=env, capture_output=True, check=True, timeout=300
            )
            # gzip manually
            gz = subprocess.run(
                ["gzip", "-c"],
                input=dump.stdout,
                capture_output=True,
                check=True,
                timeout=300,
            )
            out.write(gz.stdout)

    @staticmethod
    def _run_pg_restore(db_url: str, input_path: Path) -> None:
        """Decompress and pipe to psql."""
        import os

        user, password, host, port, dbname = BackupService._parse_db_url(db_url)

        # Merge into existing environment (same rationale as _run_pg_dump)
        env = {**os.environ, "PGPASSWORD": password}

        # Decompress
        gz = subprocess.run(
            ["gunzip", "-c", str(input_path)],
            capture_output=True,
            check=True,
            timeout=300,
        )

        # Restore
        cmd = [
            "psql",
            "-h", host,
            "-p", port,
            "-U", user,
            "-d", dbname,
        ]
        subprocess.run(
            cmd, input=gz.stdout, env=env,
            capture_output=True, check=True, timeout=300,
        )

    @staticmethod
    async def _get_schema_version() -> str:
        """Return the current Alembic schema version, or 'unknown'."""
        try:
            result = subprocess.run(
                ["alembic", "current"],
                capture_output=True, text=True, timeout=10
            )
            # Output line looks like: "abc123 (head)"
            for line in result.stdout.splitlines():
                line = line.strip()
                if line:
                    return line.split()[0]
        except Exception:
            pass
        return "unknown"
