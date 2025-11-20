#!/bin/bash
#
# PostgreSQL Database Backup Script
#
# Creates compressed backups of the Zenzefi PostgreSQL database.
# Backups are stored locally with automatic cleanup of old backups.
# Optional upload to S3/Backblaze for off-site storage.
#
# Usage:
#   ./backup_database.sh
#
# Environment Variables (optional):
#   BACKUP_DIR - Backup directory (default: /var/backups/zenzefi)
#   POSTGRES_HOST - PostgreSQL host (default: localhost)
#   POSTGRES_USER - PostgreSQL user (default: zenzefi)
#   POSTGRES_DB - Database name (default: zenzefi_db)
#   S3_BUCKET - S3 bucket for off-site backup (optional)
#   RETENTION_DAYS - Days to keep backups (default: 30)
#

set -e  # Exit on error
set -u  # Exit on undefined variable

# ===== CONFIGURATION =====
BACKUP_DIR="${BACKUP_DIR:-/var/backups/zenzefi}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_USER="${POSTGRES_USER:-zenzefi}"
POSTGRES_DB="${POSTGRES_DB:-zenzefi_db}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
S3_BUCKET="${S3_BUCKET:-}"  # Optional, e.g., s3://zenzefi-backups

# Timestamp for backup file
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/zenzefi_backup_${TIMESTAMP}.sql.gz"

# ===== FUNCTIONS =====
log_info() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1"
}

log_error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
}

# ===== MAIN =====
log_info "Starting PostgreSQL backup..."

# Create backup directory if it doesn't exist
if [ ! -d "${BACKUP_DIR}" ]; then
    log_info "Creating backup directory: ${BACKUP_DIR}"
    mkdir -p "${BACKUP_DIR}"
fi

# Backup PostgreSQL database
log_info "Backing up database: ${POSTGRES_DB}"
log_info "Output file: ${BACKUP_FILE}"

if pg_dump -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" | gzip > "${BACKUP_FILE}"; then
    log_info "Database backup completed successfully"

    # Get backup file size
    BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    log_info "Backup size: ${BACKUP_SIZE}"
else
    log_error "Database backup failed!"
    exit 1
fi

# Upload to S3/Backblaze (optional)
if [ -n "${S3_BUCKET}" ]; then
    log_info "Uploading backup to S3: ${S3_BUCKET}"

    if command -v aws &> /dev/null; then
        if aws s3 cp "${BACKUP_FILE}" "${S3_BUCKET}/"; then
            log_info "Backup uploaded to S3 successfully"
        else
            log_error "Failed to upload backup to S3"
        fi
    else
        log_error "AWS CLI not found, skipping S3 upload"
    fi
fi

# Cleanup old backups (retention policy)
log_info "Cleaning up old backups (retention: ${RETENTION_DAYS} days)"
find "${BACKUP_DIR}" -name "zenzefi_backup_*.sql.gz" -mtime +${RETENTION_DAYS} -delete

# Count remaining backups
BACKUP_COUNT=$(find "${BACKUP_DIR}" -name "zenzefi_backup_*.sql.gz" | wc -l)
log_info "Total backups: ${BACKUP_COUNT}"

log_info "Backup process completed successfully"
exit 0
