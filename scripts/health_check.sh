#!/usr/bin/env bash
# ============================================================
# Slidein Instance Health Check
#
# Inspects running services, ports, and external HTTPS endpoints:
# - slidein-api (:8100)
# - slidein-app (:3000)
# - KumoMTA (:2587)
# - GoPhish (:8333)
# - Warmbly (:5173 / :8180)
# - Caddy reverse proxy & TLS
# ============================================================
set -euo pipefail

BASE_DOMAIN="${1:-}"

log()  { echo "==> $*"; }
pass() { echo "  [PASS] $*"; }
fail() { echo "  [FAIL] $*" >&2; }
warn() { echo "  [WARN] $*" >&2; }

FAILED=0

echo "================================================"
echo "  Slidein Instance Health Check"
echo "================================================"

# 1. Slidein Workflow API (:8100)
log "Checking Slidein Workflow API (127.0.0.1:8100)..."
if curl -fsSL --max-time 5 http://127.0.0.1:8100/health > /dev/null 2>&1; then
  pass "slidein-api is healthy on :8100"
else
  fail "slidein-api is NOT responding on :8100"
  FAILED=$((FAILED + 1))
fi

# 2. Slidein Client Dashboard (:3000)
log "Checking Slidein Client Dashboard (127.0.0.1:3000)..."
if curl -fsSL --max-time 5 http://127.0.0.1:3000/api/healthz > /dev/null 2>&1 || (echo > /dev/tcp/127.0.0.1/3000) 2>/dev/null; then
  pass "slidein-app is healthy on :3000"
else
  fail "slidein-app is NOT responding on :3000"
  FAILED=$((FAILED + 1))
fi

# 3. KumoMTA SMTP Egress (:2587)
log "Checking KumoMTA Outbound Engine (127.0.0.1:2587)..."
if (echo > /dev/tcp/127.0.0.1/2587) 2>/dev/null; then
  pass "KumoMTA listening on port 2587"
else
  warn "KumoMTA not responding on port 2587 (inbound relay down or cold IP mode)"
fi

# 4. GoPhish Campaign Console (:8333)
log "Checking GoPhish Admin Service (127.0.0.1:8333)..."
if (echo > /dev/tcp/127.0.0.1/8333) 2>/dev/null; then
  pass "GoPhish listening on port 8333"
else
  warn "GoPhish not responding on port 8333"
fi

# 5. Warmbly Warmup Engine (:5173 / :8180)
log "Checking Warmbly Warmup Engine (:5173)..."
if (echo > /dev/tcp/127.0.0.1/5173) 2>/dev/null || (echo > /dev/tcp/127.0.0.1/8180) 2>/dev/null; then
  pass "Warmbly warmup platform is active"
else
  warn "Warmbly not detected (normal if --minimal flag was used)"
fi

# 6. External HTTPS (if base domain provided)
if [ -n "$BASE_DOMAIN" ]; then
  log "Checking external HTTPS endpoints for $BASE_DOMAIN..."
  for h in "app.$BASE_DOMAIN" "api.$BASE_DOMAIN/health"; do
    code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 "https://$h" 2>&1 || echo "000")
    if [ "$code" = "200" ]; then
      pass "https://$h -> 200 OK"
    else
      warn "https://$h -> HTTP $code (check DNS propagation & Caddy certs)"
    fi
  done
fi

echo "================================================"
if [ "$FAILED" -eq 0 ]; then
  echo "  ALL CORE SERVICES HEALTHY"
  exit 0
else
  echo "  $FAILED CORE SERVICE(S) REPORTED ISSUES" >&2
  exit 1
fi
