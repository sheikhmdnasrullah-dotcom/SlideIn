#!/usr/bin/env bash
# Backup lab config + volume data (NOT secret material content beyond mounted).
set -euo pipefail
OUT="${1:-kumolab-backup-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE/compose"
cp docker-compose.yml "$OUT"/
cp -r ../policy ../monitoring ../dkim "$OUT"/ 2>/dev/null || true
# Volume data (best-effort; volume name may differ by project)
for v in kumomta-lab_kumo-data kumomta-lab_sink-data kumomta-lab_redis-data; do
  docker run --rm -v "$v:/data" -v "$PWD/$OUT":/backup alpine sh -c "tar czf /backup/$v.tgz -C /data ." 2>/dev/null \
    && echo "backed up $v" || echo "skip $v (not present)"
done
echo "Backup written to $OUT"
