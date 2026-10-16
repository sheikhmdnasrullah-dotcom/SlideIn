#!/usr/bin/env bash
# ============================================================
# Slidein Instance Backup Script
#
# Creates a timestamped, compressed backup archive of:
# - SQLite database (/opt/slidein/slidein-api/data/slidein.db)
# - Secrets file (/opt/slidein/.secrets.env)
# - Caddyfile configuration (/etc/caddy/Caddyfile)
# - Deliverability config (/opt/deliverability/config.json)
#
# Usage:
#   ./scripts/backup_instance.sh [--dest /custom/backup/dir]
# ============================================================
set -euo pipefail

DEST_DIR="${1:-/opt/slidein/backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="slidein_backup_${TIMESTAMP}"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "================================================"
echo "  Slidein Instance Backup"
echo "  Timestamp: $TIMESTAMP"
echo "================================================"

mkdir -p "$DEST_DIR" "$TMP_DIR/$BACKUP_NAME"

# 1. Database snapshot
DB_SRC=""
for p in "/opt/slidein/slidein-api/data/slidein.db" "$(dirname "$0")/../slidein-api/data/slidein.db" "/opt/slidein/repo/slidein-api/data/slidein.db"; do
  if [ -f "$p" ]; then DB_SRC="$p"; break; fi
done

if [ -n "$DB_SRC" ]; then
  echo "==> Backing up database from $DB_SRC..."
  if command -v sqlite3 > /dev/null 2>&1; then
    sqlite3 "$DB_SRC" ".backup '$TMP_DIR/$BACKUP_NAME/slidein.db'"
  else
    cp "$DB_SRC" "$TMP_DIR/$BACKUP_NAME/slidein.db"
  fi
  chmod 600 "$TMP_DIR/$BACKUP_NAME/slidein.db"
else
  echo "WARN: No SQLite database found to back up."
fi

# 2. Secrets
for sec in "/opt/slidein/.secrets.env" "$(dirname "$0")/../slidein-api/.env"; do
  if [ -f "$sec" ]; then
    echo "==> Backing up secrets from $sec..."
    cp "$sec" "$TMP_DIR/$BACKUP_NAME/secrets.env"
    chmod 600 "$TMP_DIR/$BACKUP_NAME/secrets.env"
    break
  fi
done

# 3. Caddyfile
if [ -f "/etc/caddy/Caddyfile" ]; then
  echo "==> Backing up Caddyfile..."
  cp "/etc/caddy/Caddyfile" "$TMP_DIR/$BACKUP_NAME/Caddyfile"
fi

# 4. Deliverability config
if [ -f "/opt/deliverability/config.json" ]; then
  echo "==> Backing up deliverability config..."
  cp "/opt/deliverability/config.json" "$TMP_DIR/$BACKUP_NAME/deliverability_config.json"
fi

# 5. Create compressed archive
ARCHIVE_PATH="$DEST_DIR/${BACKUP_NAME}.tar.gz"
echo "==> Packaging archive: $ARCHIVE_PATH..."
tar -czf "$ARCHIVE_PATH" -C "$TMP_DIR" "$BACKUP_NAME"
chmod 600 "$ARCHIVE_PATH"

# 6. Retention: keep latest 7 backups
echo "==> Pruning backups older than 7 copies..."
find "$DEST_DIR" -name "slidein_backup_*.tar.gz" -type f | sort -r | tail -n +8 | xargs -r rm -f

BACKUP_SIZE=$(du -h "$ARCHIVE_PATH" | cut -f1)
echo "================================================"
echo "  BACKUP COMPLETE"
echo "  File: $ARCHIVE_PATH ($BACKUP_SIZE)"
echo "================================================"
echo "Restore instructions:"
echo "  1. Stop services: systemctl stop slidein-api && pm2 stop slidein-app"
echo "  2. Extract: tar -xzf $ARCHIVE_PATH -C /tmp"
echo "  3. Restore DB: cp /tmp/$BACKUP_NAME/slidein.db /opt/slidein/slidein-api/data/slidein.db"
echo "  4. Restart services: systemctl start slidein-api && pm2 start slidein-app"
