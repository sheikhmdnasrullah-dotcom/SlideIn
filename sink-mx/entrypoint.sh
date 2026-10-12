#!/bin/sh
# Lab sink MX entrypoint.
# Bind to 25/tcp, advertise capabilities, never relay. Replay a programmable SMTP
# scenario per recipient class so we can measure shaping outcomes.

set -eu

mkdir -p /var/lib/sink /var/log/sink

# Default scenarios file location; compose mounts the lab's YAML there.
: "${SINK_SCENARIOS_FILE:=/etc/sink/scenarios.yaml}"
: "${SINK_METRICS_ADDR:=0.0.0.0:8467}"
: "${SINK_LISTEN_ADDR:=0.0.0.0:25}"

export SINK_SCENARIOS_FILE SINK_METRICS_ADDR SINK_LISTEN_ADDR

# Run the file directly (not `python -m app.server`) to avoid the package
# double-import that skips the __main__ guard and silently exits 0.
exec python /app/app/server.py