#!/usr/bin/env bash
# Build + start the KumoMTA lab. Local-only; never reaches the Internet.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE/compose"
docker compose build
docker compose up -d
echo "Lab up."
echo "  Kumo submission : 127.0.0.1:2587 (auth: lab / see KUMO_LAB_PASSWORD)"
echo "  Kumo admin API  : 127.0.0.1:8029"
echo "  Sink metrics    : 127.0.0.1:8467/metrics"
echo "  Prometheus      : 127.0.0.1:9090"
echo "  Grafana         : 127.0.0.1:3000 (admin password in secrets/grafana_admin.txt)"
