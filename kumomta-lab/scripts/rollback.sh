#!/usr/bin/env bash
# Stop the lab and (optionally) restore the previous compose + config snapshot.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE/compose"
if [ "${1:-}" = "--restore" ] && [ -n "${2:-}" ]; then
  SNAP="$2"
  echo "Restoring config from $SNAP"
  cp -f "$SNAP/docker-compose.yml" .
  cp -rf "$SNAP/policy" "$SNAP/monitoring" "$SNAP/dkim" "$HERE"/ 2>/dev/null || true
fi
docker compose down
echo "Lab stopped."
