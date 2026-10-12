#!/bin/sh
set -eu

# SlideIn Local KumoMTA entrypoint
mkdir -p /var/lib/kumo/spool/data /var/lib/kumo/spool/meta /var/lib/kumo/logs /var/log/kumo
chown -R kumod:kumod /var/lib/kumo /var/log/kumo 2>/dev/null || true
touch /var/lib/kumo/accounting.db
chown kumod:kumod /var/lib/kumo/accounting.db 2>/dev/null || true

# Ensure dkim and policy dirs are readable
chmod -R a+r /etc/kumo/dkim 2>/dev/null || true
chmod -R a+r /etc/kumo/policy 2>/dev/null || true

POLICY_FILE="${KUMO_CONFIG_PATH:-/etc/kumo/policy/local_init.lua}"

echo "Starting SlideIn KumoMTA with policy: ${POLICY_FILE}"
exec setpriv --reuid=999 --regid=999 --init-groups \
  /opt/kumomta/sbin/kumod --policy "${POLICY_FILE}"
