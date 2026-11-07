#!/bin/bash
# Back up the database and the generated files, so the demo can be restored exactly.
#
#   scripts/backup.sh                 -> backups/<date-time>/ with database.dump, storage.tar, manifest.txt
#
# Run from the project root in WSL, with the PostgreSQL container up. backups/ is git-ignored.
# The database goes out through pg_dump inside the container (custom format, so pg_restore can
# recreate it); storage/ (uploads, processed results, crops) goes into an uncompressed tar,
# because the videos in it are already compressed.
set -euo pipefail
cd "$(dirname "$0")/.."

PGUSER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2 | tr -d '\r')
PGDB=$(grep '^POSTGRES_DB=' .env | cut -d= -f2 | tr -d '\r')
: "${PGUSER:=tracko}" "${PGDB:=tracko_anpr}"

stamp=$(date +%Y%m%d-%H%M%S)
target="backups/$stamp"
mkdir -p "$target"

echo "Dumping database $PGDB ..."
docker exec tracko-anpr-postgres pg_dump -U "$PGUSER" -d "$PGDB" -Fc > "$target/database.dump"

echo "Archiving storage/ ..."
tar -cf "$target/storage.tar" -C storage uploads processed vehicle_crops plate_crops

{
  echo "created: $(date -Iseconds)"
  echo "git commit: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "database: $PGDB as $PGUSER, pg_dump custom format"
  echo "storage: uploads processed vehicle_crops plate_crops"
  echo "videos registered from videos/ are NOT in the backup; keep that folder too."
} > "$target/manifest.txt"

du -sh "$target"/* | sed 's/^/  /'
echo "Backup written to $target"
echo "Restore with: scripts/restore.sh $target"
