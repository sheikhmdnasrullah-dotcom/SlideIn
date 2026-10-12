#!/usr/bin/env bash
# READ-ONLY audit of the VPS + Mailcow. NEVER modifies anything.
# Run on the VPS (or via: ssh root@vps 'bash -s' < scripts/audit.sh).
set -u
OUT="${1:-vps-audit-$(date +%Y%m%d-%H%M%S).txt}"
exec >"$OUT" 2>&1
echo "===== $(date -u) ====="
echo "=== OS/KERNEL ==="; uname -a; (cat /etc/os-release 2>/dev/null | head -5); uptime
echo "=== CPU/RAM/DISK ==="; nproc; free -h; df -h
echo "=== FILESYSTEM ==="; (mount | grep -E 'ext4|xfs|zfs' | head)
echo "=== DOCKER ==="; (docker version --format '{{.Server.Version}}' 2>/dev/null || echo "docker missing"); (docker compose version 2>/dev/null)
echo "=== NETWORK ==="; (ip -br addr 2>/dev/null || ifconfig -a); ip route 2>/dev/null; cat /etc/resolv.conf
echo "=== HOSTNAME/FQDN/PTR ==="; hostname; hostname -f; (dig +short $(hostname -f) 2>/dev/null)
echo "=== LISTENING PORTS ==="; (ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null)
echo "=== PORT 25 OWNER ==="; (ss -tlnp 2>/dev/null | grep ':25 ' || echo "no listener on 25")
echo "=== FIREWALL ==="; (iptables -S 2>/dev/null | head -60); (nft list ruleset 2>/dev/null | head -60); (ufw status 2>/dev/null)
echo "=== NTP ==="; (timedatectl 2>/dev/null | head)
echo "=== DOCKER CONTAINERS ==="; docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
echo "=== MAILCOW ==="; if [ -d /opt/mailcow-dockerized ]; then (cd /opt/mailcow-dockerized && docker compose ps 2>/dev/null); else echo "mailcow not at /opt/mailcow-dockerized"; fi
echo "=== MAILCOW PUBLISHED PORTS ==="; (docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -iE 'mailcow|postfix|dovecot|rspamd' )
echo "AUDIT COMPLETE -> $OUT"
