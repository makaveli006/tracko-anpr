#!/bin/bash
# Restore a backup made by scripts/backup.sh: the database and storage/ as they were.
#
#   scripts/restore.sh backups/<date-time>
#
# Run from the project root in WSL with the PostgreSQL container up and the web app and worker
# stopped. Everything currently in the database and under storage/ is replaced.
set -euo pipefail
cd "$(dirname "$0")/.."

source_dir=${1:?usage: scripts/restore.sh backups/<date-time>}
[ -f "$source_dir/database.dump" ] || { echo "No database.dump in $source_dir"; exit 1; }
[ -f "$source_dir/storage.tar" ] || { echo "No storage.tar in $source_dir"; exit 1; }

PGUSER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2 | tr -d '\r')
PGDB=$(grep '^POSTGRES_DB=' .env | cut -d= -f2 | tr -d '\r')
: "${PGUSER:=tracko}" "${PGDB:=tracko_anpr}"

echo "Restoring database $PGDB ..."
# --clean --if-exists drops the tables the dump recreates; alembic_version is in the dump too.
docker exec -i tracko-anpr-postgres pg_restore -U "$PGUSER" -d "$PGDB" --clean --if-exists --no-owner < "$source_dir/database.dump"

echo "Restoring storage/ ..."
for folder in uploads processed vehicle_crops plate_crops; do
  find "storage/$folder" -mindepth 1 ! -name .gitkeep -exec rm -rf {} + 2>/dev/null || true
done
tar -xf "$source_dir/storage.tar" -C storage

echo "Restored from $source_dir"
uv run tracko-anpr db-status | sed -n '/Rows/,/app_settings/p'
