#!/usr/bin/env bash
# ── Database Backup Script ────────────────────────────────
# Performs pg_dump and manages backup retention.
#
# Usage:
#   ./backup_db.sh [backup_dir]
#
# Schedule via cron:
#   0 2 * * * /app/scripts/backup_db.sh /backups
#
# Retention:
#   - Last 7 daily backups
#   - Last 4 weekly backups (Sunday)

set -euo pipefail

BACKUP_DIR="${1:-/home/factory/backups/db}"
DB_NAME="${POSTGRES_DB:-factory_bot}"
DB_USER="${POSTGRES_USER:-factory}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"

DATE=$(date +%Y-%m-%d)
DAY_OF_WEEK=$(date +%u)  # 1=Monday, 7=Sunday
FILENAME="factory_bot_${DATE}.sql.gz"

# Create backup directory
mkdir -p "${BACKUP_DIR}/daily"
mkdir -p "${BACKUP_DIR}/weekly"

echo "[$(date -Iseconds)] Starting backup of ${DB_NAME}..."

# Perform backup
PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --format=plain \
    --no-owner \
    --no-privileges \
    | gzip > "${BACKUP_DIR}/daily/${FILENAME}"

echo "[$(date -Iseconds)] Daily backup created: ${BACKUP_DIR}/daily/${FILENAME}"

# Weekly backup on Sunday
if [ "${DAY_OF_WEEK}" -eq 7 ]; then
    cp "${BACKUP_DIR}/daily/${FILENAME}" "${BACKUP_DIR}/weekly/${FILENAME}"
    echo "[$(date -Iseconds)] Weekly backup created: ${BACKUP_DIR}/weekly/${FILENAME}"
fi

# Retention: keep last 7 daily backups
cd "${BACKUP_DIR}/daily" || exit 1
ls -1t *.sql.gz 2>/dev/null | tail -n +8 | while read -r old_backup; do
    rm -f "${old_backup}"
    echo "[$(date -Iseconds)] Removed old daily backup: ${old_backup}"
done

# Retention: keep last 4 weekly backups
cd "${BACKUP_DIR}/weekly" || exit 1
ls -1t *.sql.gz 2>/dev/null | tail -n +5 | while read -r old_backup; do
    rm -f "${old_backup}"
    echo "[$(date -Iseconds)] Removed old weekly backup: ${old_backup}"
done

# Report backup size
BACKUP_SIZE=$(du -sh "${BACKUP_DIR}/daily/${FILENAME}" | cut -f1)
echo "[$(date -Iseconds)] Backup complete. Size: ${BACKUP_SIZE}"

# VACUUM high-write tables (only on Sundays)
if [ "${DAY_OF_WEEK}" -eq 7 ]; then
    echo "[$(date -Iseconds)] Running VACUUM ANALYZE on high-write tables..."
    PGPASSWORD="${POSTGRES_PASSWORD:-}" psql \
        -h "${DB_HOST}" \
        -p "${DB_PORT}" \
        -U "${DB_USER}" \
        -d "${DB_NAME}" \
        -c "VACUUM ANALYZE factory_events; VACUUM ANALYZE analytics;" \
        2>/dev/null || echo "[$(date -Iseconds)] VACUUM failed (non-critical)"
fi

echo "[$(date -Iseconds)] Backup script finished."
