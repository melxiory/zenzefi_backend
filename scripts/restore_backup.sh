#!/bin/bash
#
# PostgreSQL Database Restore Script
#
# Restores a PostgreSQL database from a compressed backup file.
# Stops the backend service during restore to prevent conflicts.
#
# Usage:
#   ./restore_backup.sh <backup_file.sql.gz>
#
# Example:
#   ./restore_backup.sh /var/backups/zenzefi/zenzefi_backup_20250117_030000.sql.gz
#
# Environment Variables (optional):
#   POSTGRES_HOST - PostgreSQL host (default: localhost)
#   POSTGRES_USER - PostgreSQL user (default: zenzefi)
#   POSTGRES_DB - Database name (default: zenzefi_db)
#   DOCKER_COMPOSE_FILE - Docker Compose file (default: docker-compose.yml)
#

set -e  # Exit on error
set -u  # Exit on undefined variable

# ===== CONFIGURATION =====
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_USER="${POSTGRES_USER:-zenzefi}"
POSTGRES_DB="${POSTGRES_DB:-zenzefi_db}"
DOCKER_COMPOSE_FILE="${DOCKER_COMPOSE_FILE:-docker-compose.yml}"

# ===== FUNCTIONS =====
log_info() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1"
}

log_error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
}

log_warning() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1"
}

# ===== MAIN =====

# Check if backup file is provided
if [ $# -eq 0 ]; then
    log_error "Usage: $0 <backup_file.sql.gz>"
    log_error "Example: $0 /var/backups/zenzefi/zenzefi_backup_20250117_030000.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

# Validate backup file exists
if [ ! -f "${BACKUP_FILE}" ]; then
    log_error "Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

log_info "Starting database restore from: ${BACKUP_FILE}"

# Get backup file info
BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
log_info "Backup file size: ${BACKUP_SIZE}"

# Confirm restoration (this is a destructive operation!)
log_warning "This will OVERWRITE the current database: ${POSTGRES_DB}"
read -p "Are you sure you want to continue? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    log_info "Restore operation cancelled by user"
    exit 0
fi

# Stop backend service (if using Docker Compose)
if command -v docker-compose &> /dev/null && [ -f "${DOCKER_COMPOSE_FILE}" ]; then
    log_info "Stopping backend service..."
    if docker-compose -f "${DOCKER_COMPOSE_FILE}" stop backend; then
        log_info "Backend service stopped"
    else
        log_warning "Failed to stop backend service (continuing anyway)"
    fi
else
    log_warning "Docker Compose not found or file missing, skipping service stop"
fi

# Drop existing database (optional, for clean restore)
log_info "Dropping existing database: ${POSTGRES_DB}"
psql -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};"

# Create fresh database
log_info "Creating fresh database: ${POSTGRES_DB}"
psql -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -c "CREATE DATABASE ${POSTGRES_DB};"

# Restore from backup
log_info "Restoring database from backup..."
if gunzip -c "${BACKUP_FILE}" | psql -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"; then
    log_info "Database restored successfully"
else
    log_error "Database restore failed!"
    exit 1
fi

# Start backend service (if using Docker Compose)
if command -v docker-compose &> /dev/null && [ -f "${DOCKER_COMPOSE_FILE}" ]; then
    log_info "Starting backend service..."
    if docker-compose -f "${DOCKER_COMPOSE_FILE}" start backend; then
        log_info "Backend service started"
    else
        log_error "Failed to start backend service"
        exit 1
    fi
else
    log_warning "Docker Compose not found, skipping service start"
fi

log_info "Restore process completed successfully"
log_info "Database ${POSTGRES_DB} restored from: ${BACKUP_FILE}"
exit 0
