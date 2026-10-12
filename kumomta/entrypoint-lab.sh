#!/bin/sh
set -eu

# Lab entrypoint: set up writable directories for kumod user, then run kumod.
# This runs as root initially, sets up dirs, then execs as kumod user.

# Create and chown writable directories for kumod user (uid 999)
mkdir -p /var/lib/kumo/spool/data /var/lib/kumo/spool/meta /var/lib/kumo/logs /var/log/kumo
chown -R kumod:kumod /var/lib/kumo /var/log/kumo 2>/dev/null || true

# Create accounting DB path
touch /var/lib/kumo/accounting.db
chown kumod:kumod /var/lib/kumo/accounting.db 2>/dev/null || true

# Ensure dkim dir is readable
chmod -R a+r /etc/kumo/dkim 2>/dev/null || true

# Ensure policy is readable
chmod -R a+r /etc/kumo/policy 2>/dev/null || true

# Now exec as kumod user (uid 999)
exec setpriv --reuid=999 --regid=999 --init-groups \
  /opt/kumomta/sbin/kumod --policy /etc/kumo/policy/init.lua