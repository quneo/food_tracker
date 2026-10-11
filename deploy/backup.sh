#!/bin/sh
# Backup of the food tracker: SQLite (consistent online copy, last 14 kept) and the photos
# from MinIO (mirrored as plain files). Run on the host from cron, e.g.
#   15 4 * * * /opt/food-tracker/deploy/backup.sh >> /srv/food-tracker/backups/backup.log 2>&1
set -eu

cd "$(dirname "$0")/.."
PROJECT=${COMPOSE_PROJECT_NAME:-food-tracker}
COMPOSE="docker compose -p $PROJECT -f docker-compose.yml"
[ -f compose.local.yml ] && COMPOSE="$COMPOSE -f compose.local.yml"
BACKUP_DIR=${BACKUP_DIR:-/srv/food-tracker/backups}
MC_IMAGE=${MC_IMAGE:-pgsty/mc:RELEASE.2026-09-16T00-00-00Z}

# S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET
set -a
. ./.env
set +a

echo "$(date -Is) database"
$COMPOSE exec -T backend python -m app.backup /data/backups

echo "$(date -Is) photos"
mkdir -p "$BACKUP_DIR/media"
docker run --rm \
    --network "${PROJECT}_default" \
    --user "$(id -u):$(id -g)" \
    -e MC_CONFIG_DIR=/tmp/mc \
    -e "MC_HOST_food=http://$S3_ACCESS_KEY:$S3_SECRET_KEY@minio:9000" \
    -v "$BACKUP_DIR/media:/backup" \
    "$MC_IMAGE" mirror --overwrite --remove --quiet "food/${S3_BUCKET:-food-tracker}" /backup

echo "$(date -Is) done"
