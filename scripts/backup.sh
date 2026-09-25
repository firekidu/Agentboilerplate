#!/usr/bin/env bash
# Run from repository root on VPS/EC2. Pauses API writes for a consistent backup pair.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
exec 9>.backup.lock
flock -n 9 || { echo 'Another backup is running'; exit 1; }
test -n "$(docker compose ps --status running -q api)" || { echo 'Start the API before backup'; exit 1; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)
destination="$PWD/backups/$stamp"
mkdir -p "$destination"
trap 'docker compose start api >/dev/null' EXIT
docker compose stop -t 300 api
docker compose exec -T postgres pg_dump -U rag -d rag -Fc > "$destination/postgres.dump"
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$destination:/backup" api python -m scripts.qdrant_backup /backup
git rev-parse HEAD > "$destination/revision.txt" 2>/dev/null || cp VERSION "$destination/revision.txt"
(cd "$destination" && sha256sum postgres.dump > postgres.sha256)
touch "$destination/COMPLETE"
echo "Backup complete: $destination"
echo 'Copy this directory to encrypted off-server storage. Keep .env separately in a secrets vault.'
