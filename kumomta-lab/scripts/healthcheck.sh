#!/usr/bin/env bash
# Health check for the local lab. Exits non-zero if any core service is down.
set -u
fail=0
nc_port(){ nc -z -w3 "$1" "$2" 2>/dev/null && echo "OK   $1:$2" || { echo "FAIL $1:$2"; fail=1; }; }
nc_port 127.0.0.1 2587   # kumo submission
nc_port 127.0.0.1 8029   # kumo admin
nc_port 127.0.0.1 8467   # sink metrics
curl -sf http://127.0.0.1:9090/-/healthy >/dev/null 2>&1 && echo "OK   prometheus" || { echo "FAIL prometheus"; fail=1; }
curl -sf http://127.0.0.1:3000/api/health >/dev/null 2>&1 && echo "OK   grafana" || { echo "FAIL grafana"; fail=1; }
exit $fail
