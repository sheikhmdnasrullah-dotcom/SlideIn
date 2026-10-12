#!/usr/bin/env bash
# Validate DNS auth records for a domain (SPF/DKIM/DMARC/PTR). Read-only.
set -u
DOMAIN="${1:?usage: test-dns.sh <domain> [sending-ip]}"
IP="${2:-}"
echo "=== SPF ($DOMAIN) ==="; dig +short TXT "$DOMAIN" | grep -i spf || echo "no SPF"
echo "=== DMARC (_dmarc.$DOMAIN) ==="; dig +short TXT "_dmarc.$DOMAIN" || echo "no DMARC"
echo "=== DKIM (selector from stdin/arg) ==="
read -r -p "DKIM selector: " SEL || SEL=""
[ -n "$SEL" ] && dig +short TXT "$SEL._domainkey.$DOMAIN" || echo "skip DKIM"
echo "=== MX ($DOMAIN) ==="; dig +short MX "$DOMAIN"
if [ -n "$IP" ]; then
  echo "=== PTR ($IP) ==="; dig +short -x "$IP" || echo "no PTR"
fi
