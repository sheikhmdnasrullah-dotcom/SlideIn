#!/usr/bin/env bash
# End-to-end SMTP smoke test against the lab: submit one message per scenario
# and report sink dispositions. Requires the lab running (deploy.sh).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"
python3 scripts/send-test.py "${@:-}"
