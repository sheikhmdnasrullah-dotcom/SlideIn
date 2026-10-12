#!/usr/bin/env bash
# Verify the lab DKIM private key parses and matches the public key.
set -u
KEY="${1:-../dkim/lab-private-dkim-key.pem}"
PUB="${2:-../dkim/lab-public-dkim-key.pem}"
[ -f "$KEY" ] || { echo "private key not found: $KEY"; exit 1; }
echo "=== private key OK? ==="; openssl rsa -in "$KEY" -check -noout && echo "private key valid"
echo "=== public matches private? ==="
openssl rsa -in "$KEY" -pubout 2>/dev/null | diff - <(cat "$PUB") >/dev/null && echo "MATCH" || echo "MISMATCH (regenerate pair)"
