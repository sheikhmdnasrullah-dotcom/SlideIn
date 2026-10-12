#!/usr/bin/env bash
# ============================================================
# Full Production Deployment Script
# Deploys KumoMTA + GoPhish + Monitoring for cold email deliverability
# ============================================================
set -euo pipefail

VPS="${1:-root@169.58.207.75}"
PASS="${VPS_PASS:?set VPS_PASS env var}"
KUMO_AUTH_PASS="${KUMO_AUTH_PASS:?set KUMO_AUTH_PASS env var}"
KUMO_ADMIN_PASS="${KUMO_ADMIN_PASS:-$KUMO_AUTH_PASS}"
LOCAL_ROOT="$(cd "$(dirname "$0")" && pwd)"
LAB_ROOT="$(cd "$LOCAL_ROOT/.." && pwd)"
REPO_ROOT="$(cd "$LOCAL_ROOT/../.." && pwd)"
REMOTE="/opt"

echo "================================================"
echo "  Cold Email Deliverability - Production Deploy"
echo "  VPS: $VPS"
echo "================================================"

# ============================================================
# PHASE 1: Pre-deploy checks
# ============================================================
echo ""
echo "==> PHASE 1: Pre-deploy verification"
echo "---"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "uname -a && df -h / && nproc && free -h"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "docker --version && docker compose version"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "ss -tlnp | grep -E '25|80|443' || echo 'Port check done'"

# ============================================================
# PHASE 2: Deploy KumoMTA
# ============================================================
echo ""
echo "==> PHASE 2: Deploying KumoMTA production"
echo "---"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "mkdir -p $REMOTE/kumomta-lab/policy $REMOTE/kumomta-lab/dkim $REMOTE/kumomta-lab/monitoring $REMOTE/kumomta-lab/compose $REMOTE/kumomta-lab/secrets $REMOTE/kumomta $REMOTE/kumomta/monitoring $REMOTE/kumomta/etc/policy"

# Copy all production files (paths are relative to kumomta-lab/, not scripts/)
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -r \
  "$LAB_ROOT/policy/" \
  "$LAB_ROOT/dkim/" \
  "$LAB_ROOT/monitoring/" \
  "$VPS:$REMOTE/kumomta-lab/"

# Local secrets dir is gitignored and may not exist; copy when present,
# otherwise the VPS generates what compose needs (see below).
if [ -d "$LAB_ROOT/secrets" ]; then
  sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -r \
    "$LAB_ROOT/secrets/" \
    "$VPS:$REMOTE/kumomta-lab/"
fi
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "test -f $REMOTE/kumomta-lab/secrets/grafana_admin.txt || openssl rand -base64 24 > $REMOTE/kumomta-lab/secrets/grafana_admin.txt; chmod 600 $REMOTE/kumomta-lab/secrets/grafana_admin.txt"

sshpass -p "$PASS" scp -o StrictHostKeyChecking=no \
  "$LAB_ROOT/compose/docker-compose.production.yml" \
  "$LAB_ROOT/compose/docker-compose.yml" \
  "$VPS:$REMOTE/kumomta-lab/compose/"

# Production entrypoint required by docker-compose.production.yml
# (volume mount /opt/kumomta/entrypoint.sh)
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no \
  "$REPO_ROOT/kumomta/entrypoint.sh" \
  "$VPS:$REMOTE/kumomta/entrypoint.sh"

# Create secrets.lua
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "cat > $REMOTE/kumomta/etc/policy/secrets.lua << 'SECRETEOF'
return {
  users = {
    ['outbound'] = '${KUMO_AUTH_PASS}',
    ['admin'] = '${KUMO_ADMIN_PASS}',
  },
}
SECRETEOF
chmod 600 $REMOTE/kumomta/etc/policy/secrets.lua"

# Generate DKIM keys for all domains
DOMAINS=("nasrullahtanim.me" "tanim.social" "tanim.tech")
echo ""
echo "Generating DKIM keys for all domains..."
for DOMAIN in "${DOMAINS[@]}"; do
  sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "mkdir -p $REMOTE/kumomta-lab/dkim && openssl genrsa -out $REMOTE/kumomta-lab/dkim/${DOMAIN}.private.key 2048 && chmod 600 $REMOTE/kumomta-lab/dkim/${DOMAIN}.private.key && openssl rsa -in $REMOTE/kumomta-lab/dkim/${DOMAIN}.private.key -pubout > $REMOTE/kumomta-lab/dkim/${DOMAIN}.public.key"
  echo "  [OK] DKIM key for $DOMAIN"
done

# ============================================================
# PHASE 3: Start KumoMTA
# ============================================================
echo ""
echo "==> PHASE 3: Starting KumoMTA production container"
echo "---"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "cd $REMOTE/kumomta-lab/compose && docker compose -f docker-compose.production.yml down 2>/dev/null; docker compose -f docker-compose.production.yml up -d --build"
sleep 8

echo ""
echo "KumoMTA container status:"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "docker ps --filter name=kumomta --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# ============================================================
# PHASE 4: Deploy GoPhish
# ============================================================
echo ""
echo "==> PHASE 4: Deploying GoPhish with production config"
echo "---"

# Copy production GoPhish config and production profile config
# (scp takes a single destination; one call per file)
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no \
  "$REPO_ROOT/config.json" \
  "$VPS:/root/gophish/config.json"
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no \
  "$REPO_ROOT/gophish-config-production.json" \
  "$VPS:/root/gophish-config-production.json"

# Copy GoPhish binary and certs
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no \
  "$REPO_ROOT/gophish" \
  "$REPO_ROOT/gophish_admin.crt" \
  "$REPO_ROOT/gophish_admin.key" \
  "$VPS:/root/gophish/"

# Restart GoPhish
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "systemctl restart gophish 2>/dev/null || (cd /root/gophish && nohup ./gophish > /root/gophish/gophish.log 2>&1 &)"

sleep 3

echo ""
echo "GoPhish status:"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "systemctl status gophish 2>/dev/null || echo 'GoPhish started as process'"

# ============================================================
# PHASE 5: Configure GoPhish Sending Profiles via API
# ============================================================
echo ""
echo "==> PHASE 5: Configuring GoPhish sending profiles"
echo "---"

# Configure profiles with the repo's canonical script (copied to the VPS
# first — the previous inline version was written locally but executed
# remotely, where the file never existed)
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no \
  "$REPO_ROOT/deliverability/configure-gophish-profiles.py" \
  "$VPS:/tmp/configure-gophish-profiles.py"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "KUMO_AUTH_PASS='$KUMO_AUTH_PASS' python3 /tmp/configure-gophish-profiles.py || echo 'Profile setup requires GoPhish API access'"

# ============================================================
# PHASE 6: Deploy Warmup Engine
# ============================================================
echo ""
echo "==> PHASE 6: Deploying Warmup Engine"
echo "---"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "mkdir -p $REMOTE/warmup-engine"
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -r \
  "$REPO_ROOT/warmup-engine/src" \
  "$REPO_ROOT/warmup-engine/cli.js" \
  "$REPO_ROOT/warmup-engine/package.json" \
  "$REPO_ROOT/warmup-engine/ecosystem.config.js" \
  "$REPO_ROOT/warmup-engine/config.json" \
  "$REPO_ROOT/warmup-engine/accounts.json" \
  "$VPS:$REMOTE/warmup-engine/"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "cd $REMOTE/warmup-engine && npm install 2>/dev/null || echo 'npm install skipped'"

# ============================================================
# PHASE 7: Deploy Monitoring
# ============================================================
echo ""
echo "==> PHASE 7: Deploying Monitoring Stack"
echo "---"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "docker compose -f $REMOTE/kumomta-lab/compose/docker-compose.production.yml up -d prometheus grafana alertmanager loki"

sleep 3

echo ""
echo "Monitoring stack status:"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "docker ps --filter name=prometheus --filter name=grafana --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# ============================================================
# PHASE 8: Deploy Deliverability Pipeline
# ============================================================
echo ""
echo "==> PHASE 8: Deploying Deliverability Pipeline"
echo "---"

sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -r \
  "$REPO_ROOT/deliverability/" \
  "$VPS:/opt/deliverability/"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "cd /opt/deliverability && pip3 install -r requirements.txt 2>/dev/null || echo 'pip install skipped'"

# ============================================================
# PHASE 9: Final verification
# ============================================================
echo ""
echo "==> PHASE 9: Final Verification"
echo "---"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "curl -s http://127.0.0.1:8029/metrics 2>/dev/null | head -10 || echo 'KumoMTA check done'"

echo ""
echo "================================================"
echo "  DEPLOYMENT COMPLETE"
echo "================================================"
echo ""
echo "DNS RECORDS TO ADD (Cloudflare):"
echo ""
for DOMAIN in "${DOMAINS[@]}"; do
  echo "[$DOMAIN]"
  echo "  DKIM: dkim._domainkey.$DOMAIN"
  echo "    Type: TXT"
  echo "    Value: $(sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "cat $REMOTE/kumomta-lab/dkim/${DOMAIN}.public.key" 2>/dev/null || echo 'PENDING')"
  echo ""
done

echo "SPF:"
for DOMAIN in "${DOMAINS[@]}"; do
  echo "  $DOMAIN: v=spf1 ip4:169.58.207.75 mx -all"
done
echo ""
echo "DMARC:"
for DOMAIN in "${DOMAINS[@]}"; do
  echo "  _dmarc.$DOMAIN: v=DMARC1; p=quarantine; rua=mailto:dmarc@${DOMAIN}; adkim=s; aspf=s"
done
echo ""
echo "PTR: 169.58.207.75 -> mail.nasrullahtanim.me (request from VPS host)"
echo ""
echo "SERVICES:"
echo "  KumoMTA Admin API: http://169.58.207.75:8029"
echo "  GoPhish Admin:     https://email.tanim.tech (or http://169.58.207.75:8333)"
echo "  GoPhish Landing:   http://169.58.207.75:8080"
echo "  Grafana Dashboard: http://169.58.207.75:3000"
echo "  Warmup Engine:     pm2 start ecosystem.config.js"
echo ""
echo "NEXT STEPS:"
echo "  1. Add DNS records in Cloudflare"
echo "  2. Wait 5 min for propagation"
echo "  3. Verify: ssh $VPS 'cd /opt/deliverability && python3 cli.py precheck'"
echo "  4. Seed test: python3 cli.py seed-test"
echo "  5. Start warmup: cd /opt/warmup-engine && npm start"
echo "  6. Start campaigns: python3 /opt/deliverability/campaign_worker.py"
echo ""
echo "IMPORTANT: Rotate credentials after first deployment:"
echo "  - VPS root password"
echo "  - KumoMTA outbound/admin passwords (KUMO_AUTH_PASS / KUMO_ADMIN_PASS)"
echo "  - GoPhish admin: (set in config.json)"
