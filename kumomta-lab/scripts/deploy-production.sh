#!/usr/bin/env bash
# ============================================================
# Full Production Deployment Script
# Deploys KumoMTA + GoPhish + Monitoring for cold email deliverability
# ============================================================
set -euo pipefail

VPS="${1:-root@169.58.207.75}"
VPS_IP="${VPS##*@}"
PASS="${VPS_PASS:?set VPS_PASS env var}"
KUMO_AUTH_PASS="${KUMO_AUTH_PASS:?set KUMO_AUTH_PASS env var}"
KUMO_ADMIN_PASS="${KUMO_ADMIN_PASS:-$KUMO_AUTH_PASS}"
LOCAL_ROOT="$(cd "$(dirname "$0")" && pwd)"
LAB_ROOT="$(cd "$LOCAL_ROOT/.." && pwd)"
REPO_ROOT="$(cd "$LOCAL_ROOT/../.." && pwd)"
REMOTE="/opt"
# GoPhish server binary for the target OS (override when deploying from macOS:
# build with `docker run --rm -v $PWD:/src -w /src golang:1.26 go build -o /src/gophish-linux .`)
GOPHISH_BIN="${GOPHISH_BIN:-$REPO_ROOT/gophish}"

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
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "test -f $REMOTE/kumomta-lab/secrets/grafana_admin.txt || openssl rand -base64 24 > $REMOTE/kumomta-lab/secrets/grafana_admin.txt; chmod 644 $REMOTE/kumomta-lab/secrets/grafana_admin.txt"

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
chmod 644 $REMOTE/kumomta/etc/policy/secrets.lua"

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

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "mkdir -p $REMOTE/gophish /root/gophish"

# Build the effective GoPhish config from the production template: fresh
# SMTP credentials from env, localhost relay, sanitized origins. The local
# template keeps stale values and is never copied verbatim.
python3 - "$REPO_ROOT/gophish-config-production.json" > /tmp/gophish-effective-config.json << 'PYEOF'
import json, os, sys
cfg = json.load(open(sys.argv[1]))
auth = os.environ["KUMO_AUTH_PASS"]
cfg["smtp"]["host"] = "127.0.0.1"
cfg["smtp"]["password"] = auth
cfg["smtp"]["trusted_origins"] = ["127.0.0.1", "localhost"]
cfg["admin_server"]["trusted_origins"] = ["127.0.0.1:8333", "localhost:8333", "127.0.0.1", "localhost"]
for p in cfg.get("profiles", []):
    p["smtp_host"] = "127.0.0.1"
    p["smtp_password"] = auth
json.dump(cfg, sys.stdout, indent=2)
PYEOF
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no \
  /tmp/gophish-effective-config.json \
  "$VPS:/root/gophish/config.json"
rm -f /tmp/gophish-effective-config.json

# Copy GoPhish binary and certs
file "$GOPHISH_BIN" | grep -q 'ELF.*x86-64' || { echo "ERROR: $GOPHISH_BIN is not a Linux x86-64 binary"; exit 1; }
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no \
  "$GOPHISH_BIN" \
  "$REPO_ROOT/gophish_admin.crt" \
  "$REPO_ROOT/gophish_admin.key" \
  "$VPS:/root/gophish/"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "mv /root/gophish/$(basename "$GOPHISH_BIN") /root/gophish/gophish 2>/dev/null; chmod +x /root/gophish/gophish; ls -la /root/gophish/gophish"
# Runtime assets the binary reads from its working directory
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -r \
  "$REPO_ROOT/VERSION" \
  "$REPO_ROOT/static" \
  "$REPO_ROOT/templates" \
  "$REPO_ROOT/db" \
  "$VPS:/root/gophish/"

# Restart GoPhish
# Stable GoPhish API key (generated once, reused across reruns), injected
# into the live config before first start.
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "test -f /root/gophish/api_key.txt || openssl rand -hex 32 > /root/gophish/api_key.txt; chmod 600 /root/gophish/api_key.txt; python3 -c 'import json; k=open(\"/root/gophish/api_key.txt\").read().strip(); p=\"/root/gophish/config.json\"; c=json.load(open(p)); c[\"api_key\"]=k; json.dump(c, open(p,\"w\"), indent=2)'"
# Install the systemd unit first so `restart` succeeds; the nohup fallback
# detaches stdin or the ssh session never returns (observed 20+ min hang).
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no \
  "$LAB_ROOT/scripts/gophish.service" \
  "$VPS:/etc/systemd/system/gophish.service"
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "systemctl daemon-reload && systemctl enable gophish 2>/dev/null; systemctl restart gophish 2>/dev/null || (cd /root/gophish && nohup ./gophish > /root/gophish/gophish.log 2>&1 < /dev/null & sleep 2)"

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
# Profiles via authenticated localhost API (GoPhish was started in Phase 4).
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "for i in \$(seq 1 30); do (echo > /dev/tcp/127.0.0.1/8333) 2>/dev/null && break; sleep 2; done; GOPHISH_API_URL=http://127.0.0.1:8333/api GOPHISH_API_KEY=\$(cat /root/gophish/api_key.txt) KUMO_SMTP_HOST=127.0.0.1 KUMO_AUTH_PASS='$KUMO_AUTH_PASS' python3 /tmp/configure-gophish-profiles.py || echo 'Profile setup failed - check GoPhish API access'"

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

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "mkdir -p $REMOTE/deliverability"
# rsync (not scp -r): trailing-slash copies *contents*, so reruns never nest.
sshpass -p "$PASS" rsync -a --rsh="ssh -o StrictHostKeyChecking=no" \
  "$REPO_ROOT/deliverability/" \
  "$VPS:/opt/deliverability/"

sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$VPS" "cd /opt/deliverability && pip3 install --break-system-packages -r requirements.txt 2>/dev/null || echo 'pip install skipped'"

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
  echo "  $DOMAIN: v=spf1 ip4:$VPS_IP mx -all"
done
echo ""
echo "DMARC:"
for DOMAIN in "${DOMAINS[@]}"; do
  echo "  _dmarc.$DOMAIN: v=DMARC1; p=quarantine; rua=mailto:dmarc@${DOMAIN}; adkim=s; aspf=s"
done
echo ""
echo "PTR: $VPS_IP -> mail.nasrullahtanim.me (request from VPS host)"
echo ""
echo "SERVICES (loopback-bound; use ssh -L to reach from laptop):"
echo "  KumoMTA Admin API: http://127.0.0.1:8029"
echo "  GoPhish Admin:     http://127.0.0.1:8333"
echo "  GoPhish Landing:   http://127.0.0.1:8080"
echo "  Grafana Dashboard: http://127.0.0.1:3000"
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
