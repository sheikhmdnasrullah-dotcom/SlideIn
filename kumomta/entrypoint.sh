#!/bin/sh
set -eu

mkdir -p /var/lib/kumo/spool/data /var/lib/kumo/spool/meta /var/lib/kumo/logs /var/log/kumo
chown -R kumod:kumod /var/lib/kumo /var/log/kumo 2>/dev/null || true
touch /var/lib/kumo/accounting.db
chown kumod:kumod /var/lib/kumo/accounting.db 2>/dev/null || true
chmod -R a+r /etc/kumo/dkim 2>/dev/null || true
chmod -R a+r /etc/kumo/policy 2>/dev/null || true

exec setpriv --reuid=999 --regid=999 --init-groups \
  /opt/kumomta/sbin/kumod --policy /etc/kumo/policy/production_init.lua
