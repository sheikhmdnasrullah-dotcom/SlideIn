#!/usr/bin/env bash
# Restore a backup produced by backup.sh.
set -euo pipefail
SNAP="${1:?usage: restore.sh <backup-dir>}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE/compose"
cp -f "$SNAP/docker-compose.yml" .
cp -rf "$SNAP/policy" "$SNAP/monitoring" "$SNAP/dkim" "$HERE"/ 2>/dev/null || true
for v in kumomta-lab_kumo-data kumomta-lab_sink-data kumomta-lab_redis-data; do
  [ -f "$SNAP/$v.tgz" ] || continue
  docker run --rm -v "$v:/data" -v "$PWD/$SNAP":/backup alpine sh -c "cd /data && tar xzf /backup/$v.tgz" 2>/dev/null \
    && echo "restored $v" || echo "skip $v"
done
echo "Restore complete. Run deploy.sh to start."
