#!/usr/bin/env bash
# ============================================================
# SlideIn one-command installer — runs ON the target machine.
#
# Installs the full self-hosted stack on a fresh Ubuntu VPS:
# KumoMTA + GoPhish + dashboard + Caddy (HTTPS) + monitoring,
# lead verification (Reacher), Warmbly warmup, deliverability CLI.
#
# Usage (fresh VPS, as root):
#   curl -fsSL https://raw.githubusercontent.com/sheikhmdnasrullah-dotcom/SlideIn/main/install.sh \
#     | bash -s -- --base-domain client.com \
#                --mail-domains send1.com,send2.com \
#                --admin-email you@client.com
#
# From a git clone (contributors):
#   ./install.sh --base-domain ... --mail-domains ... --admin-email ...
#
# Flags: --senders hello,talk,connect  --minimal (skip Warmbly)
#        --non-interactive  --dry-run  --regenerate-secrets  --help
#
# Idempotent: safe to rerun; existing secrets/keys/data are kept.
# License: MIT. All bundled upstreams are permissive-licensed
# (Apache-2.0 / MIT) — see NOTICE. No paid licenses required.
# ============================================================
set -euo pipefail

INSTALL_VERSION="0.2.0"
MAIN_REPO="https://github.com/sheikhmdnasrullah-dotcom/SlideIn.git"
APP_REPO="https://github.com/sheikhmdnasrullah-dotcom/slideinventure-workspace.git"

# ---- args ----
BASE_DOMAIN=""; MAIL_DOMAINS=""; ADMIN_EMAIL=""; SENDERS="hello,talk,connect"
NON_INTERACTIVE=0; DRY_RUN=0; MINIMAL=0; REGEN_SECRETS=0

usage() {
  sed -n '2,24p' "$0"
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --base-domain) BASE_DOMAIN="${2:?}"; shift 2 ;;
    --mail-domains) MAIL_DOMAINS="${2:?}"; shift 2 ;;
    --admin-email) ADMIN_EMAIL="${2:?}"; shift 2 ;;
    --senders) SENDERS="${2:?}"; shift 2 ;;
    --non-interactive) NON_INTERACTIVE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --minimal) MINIMAL=1; shift ;;
    --regenerate-secrets) REGEN_SECRETS=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "ERROR: unknown arg: $1" >&2; usage 1 ;;
  esac
done

# ---- helpers ----
log()  { echo "==> $*"; }
warn() { echo "WARN: $*" >&2; }
die()  { echo "ERROR: $*" >&2; exit 1; }
dry()  { [ "$DRY_RUN" = 1 ] && { log "[dry-run] would: $*"; return 0; }; return 1; }

valid_domain() { [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$ ]]; }
valid_email()  { [[ "$1" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]]; }

[ -n "$BASE_DOMAIN" ] || die "missing --base-domain (hosts the dashboard: app.<base>)"
[ -n "$MAIL_DOMAINS" ] || die "missing --mail-domains (comma-separated sender domains)"
[ -n "$ADMIN_EMAIL" ] || die "missing --admin-email (contact + default sender identity)"
valid_domain "$BASE_DOMAIN" || die "bad --base-domain: $BASE_DOMAIN"
valid_email "$ADMIN_EMAIL" || die "bad --admin-email: $ADMIN_EMAIL"
IFS=',' read -ra DOMAINS <<< "$MAIL_DOMAINS"
[ "${#DOMAINS[@]}" -ge 1 ] || die "need at least one --mail-domains entry"
for d in "${DOMAINS[@]}"; do valid_domain "$d" || die "bad mail domain: $d"; done
IFS=',' read -ra SENDER_LIST <<< "$SENDERS"
[ "${#SENDER_LIST[@]}" -ge 1 ] || die "need at least one --senders entry"

PRIMARY="${DOMAINS[0]}"
APP_HOST="app.$BASE_DOMAIN"; CONSOLE_HOST="console.$BASE_DOMAIN"
TRACK_HOST="track.$BASE_DOMAIN"; WARM_HOST="warmbly.$BASE_DOMAIN"
WARM_API="warmbly-api.$BASE_DOMAIN"; WARM_TRACK="warmbly-track.$BASE_DOMAIN"
MAIL_HOST="mail.$PRIMARY"
FIRST_PROFILE="${SENDER_LIST[0]}@${DOMAINS[0]}"

SLIDEIN=/opt/slidein; REPO=$SLIDEIN/repo; APP_SRC=$SLIDEIN/workspace-app
KUMO_LAB=/opt/kumomta-lab; GOPH=/root/gophish; DELIV=/opt/deliverability
REACH=/opt/reacher/job_api; WARMB=/opt/warmbly; APPDST=/var/www/workspace-app
SECRETS_FILE=$SLIDEIN/.secrets.env

echo "================================================"
echo "  SlideIn installer v$INSTALL_VERSION"
echo "  base: $BASE_DOMAIN   mail: $MAIL_DOMAINS"
echo "================================================"

# ============================================================
# PHASE 1: preflight
# ============================================================
log "PHASE 1: preflight"
if [ "$DRY_RUN" = 1 ]; then
  warn "dry-run: environment checks relaxed (runs anywhere; install needs root + Ubuntu x86_64)"
else
  [ "$(id -u)" = 0 ] || die "run as root (or with sudo)"
  [ "$(uname -m)" = "x86_64" ] || die "only x86_64 is supported"
fi
if [ -r /etc/os-release ]; then . /etc/os-release; fi
[ "${ID:-}" = "ubuntu" ] || warn "not Ubuntu (${ID:-unknown}) — apt steps assume Ubuntu"
MEM_GB=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}' || true); MEM_GB=${MEM_GB:-0}
[ "$MEM_GB" -ge 4 ] 2>/dev/null || warn "only ${MEM_GB}GB RAM detected — 4GB+ recommended (Warmbly is heavy)"
DISK_GB=$(df -BG / 2>/dev/null | awk 'NR==2{gsub("G","",$4); print $4}' || true); DISK_GB=${DISK_GB:-0}
[ "$DISK_GB" -ge 20 ] 2>/dev/null || warn "only ${DISK_GB}GB free disk — 20GB+ recommended"
for p in 25 80 443; do
  if (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null; then
    warn "something already listens on port $p — install continues, Caddy/SMTP may conflict"
  fi
done
PUBLIC_IP=$(curl -fsSL --max-time 10 ifconfig.me 2>/dev/null || curl -fsSL --max-time 10 api.ipify.org 2>/dev/null || true)
if [ -z "$PUBLIC_IP" ]; then
  [ "$DRY_RUN" = 1 ] && { PUBLIC_IP="192.0.2.10"; warn "dry-run: using placeholder IP $PUBLIC_IP"; } || die "could not detect public IP (need outbound HTTPS)"
fi
log "public IP: $PUBLIC_IP"
# Port 25 egress is non-negotiable for an MTA.
P25_OK=0
if [ "$DRY_RUN" = 0 ]; then
for mx in mx.zoho.com gmail-smtp-in.l.google.com; do
  if timeout 8 bash -c "cat < /dev/null > /dev/tcp/$mx/25" 2>/dev/null; then P25_OK=1; break; fi
done
fi
if [ "$P25_OK" = 0 ] && [ "$DRY_RUN" = 0 ]; then
  msg="port 25 outbound is BLOCKED — request unblocking from your VPS host, then rerun"
  [ "$NON_INTERACTIVE" = 1 ] && die "$msg" || { warn "$msg"; read -rp "Continue anyway? [y/N] " c; [ "$c" = y ] || exit 1; }
fi
# DNS pre-check (informational — records are printed at the end).
A_HIT=$(dig +short A "$APP_HOST" 2>/dev/null | head -1 || true)
if [ "$A_HIT" = "$PUBLIC_IP" ]; then log "DNS already points $APP_HOST here"; else warn "$APP_HOST does not resolve here yet — HTTPS/Caddy verify waits until you add DNS (records printed at the end)"; fi

# ============================================================
# PHASE 2: system dependencies
# ============================================================
log "PHASE 2: system dependencies"
dry "apt install + docker + caddy + node20 + pm2 + ufw" || {
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg openssl python3 python3-venv python3-pip jq dnsutils rsync git ufw openssh-server > /dev/null
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
docker compose version >/dev/null || die "docker compose plugin missing after docker install"
# Caddy (official apt repo).
if ! command -v caddy >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /etc/apt/keyrings/caddy-stable.gpg
  chmod 0644 /etc/apt/keyrings/caddy-stable.gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | tee /etc/apt/sources.list.d/caddy-stable.list > /dev/null
  apt-get update -qq && apt-get install -y -qq caddy
fi
# Node 20 (proven with this dashboard) + pm2.
if ! command -v node >/dev/null || ! node --version | grep -q "v20\."; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y -qq nodejs
fi
command -v pm2 >/dev/null || npm install -g pm2 > /dev/null 2>&1
# Firewall: ssh (detected port) + mail/web. Never lock out the current session.
SSH_PORTS=$(sshd -T 2>/dev/null | awk '/^port /{print $2}' | tr '\n' ' ' || true)
[ -n "$SSH_PORTS" ] || SSH_PORTS="22"
for p in $SSH_PORTS; do ufw allow "$p"/tcp > /dev/null 2>&1 || true; done
ufw allow 25/tcp > /dev/null 2>&1 || true
ufw allow 80/tcp > /dev/null 2>&1 || true
ufw allow 443/tcp > /dev/null 2>&1 || true
ufw --force enable > /dev/null 2>&1 || true
log "deps OK: $(docker --version | head -c 30), $(caddy version | head -c 20), $(node --version), ufw active"
}

# ============================================================
# PHASE 3: layout + sources
# ============================================================
log "PHASE 3: layout + sources"
dry "clone $MAIN_REPO + dashboard repo to $SLIDEIN" || {
mkdir -p "$SLIDEIN" "$KUMO_LAB"/{policy,dkim,monitoring,compose,secrets} \
  /opt/kumomta/etc/policy /root/gophish "$DELIV" "$REACH" "$WARMB" "$APPDST"
if [ -f ./install.sh ] && [ -d ./kumomta-lab ]; then
  log "local repo detected — copying instead of cloning"
  cp -a . "$REPO.tmp" && rm -rf "$REPO" && mv "$REPO.tmp" "$REPO"
  if [ -d ./workspace-app ] && [ ! -e "$APP_SRC" ]; then cp -a ./workspace-app "$APP_SRC"; fi
else
  [ -d "$REPO/.git" ] || git clone --depth 1 "$MAIN_REPO" "$REPO"
  (cd "$REPO" && git pull --ff-only 2>/dev/null || true)
fi
[ -d "$APP_SRC/.git" ] || git clone --depth 1 "$APP_REPO" "$APP_SRC"
(cd "$APP_SRC" && git pull --ff-only 2>/dev/null || true)
[ -f "$REPO/kumomta-lab/policy/production_init.lua" ] || die "main repo incomplete (policy missing)"
[ -f "$APP_SRC/package.json" ] || die "dashboard repo incomplete (package.json missing)"
}

# ============================================================
# PHASE 4: secrets (generated once, reused on reruns)
# ============================================================
log "PHASE 4: secrets"
dry "generate service secrets in $SECRETS_FILE" || {
touch "$SECRETS_FILE" && chmod 600 "$SECRETS_FILE"
# shellcheck disable=SC1090
[ -s "$SECRETS_FILE" ] && . "$SECRETS_FILE"
gen() { # gen VAR [bytes]: set + persist unless present (or regen forced)
  local var="$1" n="${2:-24}" cur=""
  cur="$(grep -E "^$var=" "$SECRETS_FILE" 2>/dev/null | cut -d= -f2- || true)"
  if [ -z "$cur" ] || [ "$REGEN_SECRETS" = 1 ]; then
    cur="$(openssl rand -hex "$n")"
    grep -v -E "^$var=" "$SECRETS_FILE" > "$SECRETS_FILE.tmp" 2>/dev/null || true
    echo "$var=$cur" >> "$SECRETS_FILE.tmp"; mv "$SECRETS_FILE.tmp" "$SECRETS_FILE"
    chmod 600 "$SECRETS_FILE"
  fi
  export "$var=$cur"
}
gen KUMO_AUTH_PASS; gen KUMO_ADMIN_PASS; gen GOPHISH_API_KEY 32
gen GRAFANA_ADMIN; gen JOB_API_SECRET; gen REACHER_SECRET
gen INTERNAL_API_SECRET; gen VAULT_MASTER_KEY 32
# shellcheck disable=SC1090
. "$SECRETS_FILE"
echo "$GOPHISH_API_KEY" > /root/gophish/api_key.txt && chmod 600 /root/gophish/api_key.txt
log "secrets ready (kept in $SECRETS_FILE, mode 600)"
}

# ============================================================
# PHASE 5: DKIM keys (one per sender domain)
# ============================================================
log "PHASE 5: DKIM keys"
dry "openssl genrsa per mail domain" || {
for d in "${DOMAINS[@]}"; do
  if [ -f "$KUMO_LAB/dkim/$d.private.key" ]; then log "  $d: key exists, kept"; continue; fi
  openssl genrsa -out "$KUMO_LAB/dkim/$d.private.key" 2048 2>/dev/null
  chmod 600 "$KUMO_LAB/dkim/$d.private.key"
  openssl rsa -in "$KUMO_LAB/dkim/$d.private.key" -pubout > "$KUMO_LAB/dkim/$d.public.key" 2>/dev/null
  log "  $d: key generated"
done
}

# ============================================================
# PHASE 6: KumoMTA (policy + compose parameterized, then start)
# ============================================================
log "PHASE 6: KumoMTA"
dry "parameterize policy+compose, start kumomta + monitoring" || {
# shellcheck disable=SC1090
. "$SECRETS_FILE"
cp -r "$REPO/kumomta-lab/policy/" "$REPO/kumomta-lab/monitoring/" "$KUMO_LAB/"
PRIMARY="$PRIMARY" MAIL_HOST="$MAIL_HOST" MAIL_DOMAINS="$MAIL_DOMAINS" python3 - "$KUMO_LAB/policy/production_init.lua" << 'PYEOF'
import os, sys
p = sys.argv[1]
src = open(p).read()
primary, mailhost = os.environ["PRIMARY"], os.environ["MAIL_HOST"]
doms = os.environ["MAIL_DOMAINS"].split(",")
# Generic per-domain egress: the shipped file maps the author's domains;
# clients get one egress identity (EHLO), DKIM stays per-sender-domain.
old_block = """local function get_source_for_domain(domain)
  if domain == 'nasrullahtanim.me' then
    return 'mail.nasrullahtanim.me'
  elseif domain == 'tanim.social' then
    return 'email.tanim.tech'
  elseif domain == 'tanim.tech' then
    return 'email.tanim.tech'
  end
  return 'mail.nasrullahtanim.me'
end"""
assert old_block in src, "policy egress block drifted — update installer"
new_block = ("local function get_source_for_domain(domain)\n"
             "  -- Single-install deployment: every sender domain egresses\n"
             "  -- under one server identity. DKIM still signs per domain.\n"
             f"  return '{mailhost}'\nend")
src = src.replace(old_block, new_block)
assert src.count("mail.nasrullahtanim.me") >= 2, "policy mail-host refs missing"
src = src.replace("mail.nasrullahtanim.me", mailhost)
old_domains = """local DOMAINS = {
  'nasrullahtanim.me',
  'tanim.social',
  'tanim.tech',
}"""
assert old_domains in src, "policy DOMAINS block drifted"
src = src.replace(old_domains, "local DOMAINS = {\n" + "".join(f"  '{d}',\n" for d in doms) + "}")
assert "'nasrullahtanim.me'" in src, "policy fallback default missing"
src = src.replace("'nasrullahtanim.me'", f"'{primary}'")
old_note = """    -- hostname that resolves to this VPS. Never use email.tanim.tech
    -- (points at 153.76.249.166, not us)."""
assert old_note in src, "policy EHLO note drifted"
src = src.replace(old_note, "    -- hostname that resolves to this VPS (and only such a hostname).")
assert "tanim." not in src, "author domains remain in policy"
open(p, "w").write(src)
print("policy parameterized")
PYEOF
sed "s/nasrullahtanim\\.me/$PRIMARY/g" "$REPO/kumomta-lab/compose/docker-compose.production.yml" > "$KUMO_LAB/compose/docker-compose.production.yml"
grep -q "mail\.$PRIMARY" "$KUMO_LAB/compose/docker-compose.production.yml" || die "compose parameterization failed"
# Grafana admin (compose secret file).
[ -f "$KUMO_LAB/secrets/grafana_admin.txt" ] || { echo -n "$GRAFANA_ADMIN" > "$KUMO_LAB/secrets/grafana_admin.txt"; chmod 644 "$KUMO_LAB/secrets/grafana_admin.txt"; }
cp "$REPO/kumomta/entrypoint.sh" /opt/kumomta/entrypoint.sh
cat > /opt/kumomta/etc/policy/secrets.lua << SECRETEOF
return {
  users = {
    ['outbound'] = '${KUMO_AUTH_PASS}',
    ['admin'] = '${KUMO_ADMIN_PASS}',
  },
}
SECRETEOF
chmod 644 /opt/kumomta/etc/policy/secrets.lua
cd "$KUMO_LAB/compose" && docker compose -p kumomta-production -f docker-compose.production.yml up -d kumomta prometheus grafana alertmanager loki
for _ in $(seq 1 30); do curl -fsSL --max-time 3 http://127.0.0.1:8029/metrics > /dev/null 2>&1 && break; sleep 2; done
curl -fsSL --max-time 5 http://127.0.0.1:8029/metrics > /dev/null || die "KumoMTA metrics never came up"
log "KumoMTA + monitoring healthy"
}

# ============================================================
# PHASE 7: GoPhish (build, configure, start, profiles)
# ============================================================
log "PHASE 7: GoPhish"
dry "docker-build gophish, install systemd unit, create profiles" || {
# shellcheck disable=SC1090
. "$SECRETS_FILE"
mkdir -p "$REPO/build"
if [ ! -x "$REPO/build/gophish" ]; then
  docker run --rm -v "$REPO:/src" -w /src -e CGO_ENABLED=0 golang:1.26 go build -o /src/build/gophish . \
  || docker run --rm -v "$REPO:/src" -w /src -e CGO_ENABLED=0 golang:1 go build -o /src/build/gophish .
fi
file "$REPO/build/gophish" | grep -q 'ELF.*x86-64' || die "gophish build produced no linux binary"
cp "$REPO/build/gophish" "$GOPH/gophish"
chmod +x "$GOPH/gophish"
cp -r "$REPO/VERSION" "$REPO/static" "$REPO/templates" "$REPO/db" "$GOPH/"
[ -f "$GOPH/gophish_admin.crt" ] || openssl req -x509 -newkey rsa:2048 -keyout "$GOPH/gophish_admin.key" -out "$GOPH/gophish_admin.crt" -days 825 -nodes -subj "/CN=127.0.0.1" 2>/dev/null
PRIMARY="$PRIMARY" CONSOLE_HOST="$CONSOLE_HOST" CONTACT="$FIRST_PROFILE" SENDERS="$SENDERS" MAIL_DOMAINS="$MAIL_DOMAINS" KUMO_AUTH_PASS="$KUMO_AUTH_PASS" \
python3 - "$REPO/gophish-config-production.json" > "$GOPH/config.json" << 'PYEOF'
import json, os, sys
cfg = json.load(open(sys.argv[1]))
primary = os.environ["PRIMARY"]
auth = os.environ["KUMO_AUTH_PASS"]
cfg["admin_server"]["listen_url"] = "127.0.0.1:8333"
cfg["admin_server"]["use_tls"] = False
# gorilla/csrf matches referer.Host EXACTLY against bare hosts (no scheme).
cfg["admin_server"]["trusted_origins"] = ["127.0.0.1:8333", "localhost:8333", "127.0.0.1", "localhost", os.environ["CONSOLE_HOST"]]
cfg["phish_server"]["listen_url"] = "127.0.0.1:8080"
cfg["phish_server"]["use_tls"] = False
cfg["smtp"]["host"] = "127.0.0.1"
cfg["smtp"]["password"] = auth
cfg["smtp"]["trusted_origins"] = ["127.0.0.1", "localhost"]
cfg["contact_address"] = os.environ["CONTACT"]
cfg["message_id_domain"] = primary
cfg["profiles"] = [
    {"name": f"{s}@{d}", "email": f"{s}@{d}", "from_name": "", "reply_to": f"{s}@{d}",
     "smtp_host": "127.0.0.1", "smtp_password": auth}
    for d in os.environ["MAIL_DOMAINS"].split(",")
    for s in os.environ["SENDERS"].split(",")
]
assert cfg["profiles"], "no profiles generated"
json.dump(cfg, sys.stdout, indent=2)
PYEOF
python3 -c "import json; json.load(open('$GOPH/config.json'))" || die "generated gophish config is invalid JSON"
python3 -c "import json; k=open('/root/gophish/api_key.txt').read().strip(); p='$GOPH/config.json'; c=json.load(open(p)); c['api_key']=k; json.dump(c, open(p,'w'), indent=2)"
cp "$REPO/kumomta-lab/scripts/gophish.service" /etc/systemd/system/gophish.service
systemctl daemon-reload && systemctl enable gophish > /dev/null 2>&1 || true
systemctl restart gophish
for _ in $(seq 1 30); do (echo > /dev/tcp/127.0.0.1/8333) 2>/dev/null && break; sleep 2; done
(echo > /dev/tcp/127.0.0.1/8333) 2>/dev/null || die "GoPhish admin never came up"
PROFILES_JSON="$(PRIMARY="$PRIMARY" SENDERS="$SENDERS" MAIL_DOMAINS="$MAIL_DOMAINS" python3 -c "
import json, os
print(json.dumps([{'name': f'{s}@{d}', 'email': f'{s}@{d}', 'from_name': '', 'reply_to': f'{s}@{d}'} for d in os.environ['MAIL_DOMAINS'].split(',') for s in os.environ['SENDERS'].split(',')]))")"
GOPHISH_API_URL=http://127.0.0.1:8333/api GOPHISH_API_KEY="$GOPHISH_API_KEY" KUMO_SMTP_HOST=127.0.0.1 KUMO_AUTH_PASS="$KUMO_AUTH_PASS" \
  PROFILES_JSON="$PROFILES_JSON" python3 "$REPO/deliverability/configure-gophish-profiles.py" || die "profile setup failed"
log "GoPhish live with $(echo "$SENDERS" | tr ',' ' ' | wc -w)x$(echo "$MAIL_DOMAINS" | tr ',' ' ' | wc -w) profiles"
}

# ============================================================
# PHASE 8: deliverability CLI (allowlist copy — no campaign data)
# ============================================================
log "PHASE 8: deliverability CLI"
dry "copy pipeline allowlist, pip install, generate config.json" || {
# shellcheck disable=SC1090
. "$SECRETS_FILE"
mkdir -p "$DELIV"
cp -r "$REPO/deliverability/core" "$REPO/deliverability/cli.py" "$REPO/deliverability/precheck.py" \
  "$REPO/deliverability/configure-gophish-profiles.py" "$REPO/deliverability/requirements.txt" \
  "$REPO/deliverability/config.example.json" "$DELIV/"
[ -d "$REPO/deliverability/tests" ] && cp -r "$REPO/deliverability/tests" "$DELIV/" || true
find "$DELIV" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
pip3 install --break-system-packages -q -r "$DELIV/requirements.txt" || warn "pip install had issues — precheck may lack deps"
PRIMARY="$PRIMARY" PUBLIC_IP="$PUBLIC_IP" SENDERS="$SENDERS" MAIL_DOMAINS="$MAIL_DOMAINS" FIRST_PROFILE="$FIRST_PROFILE" \
KUMO_AUTH_PASS="$KUMO_AUTH_PASS" GOPHISH_API_KEY="$GOPHISH_API_KEY" python3 - "$DELIV/config.example.json" > "$DELIV/config.json" << 'PYEOF'
import json, os, sys
cfg = json.load(open(sys.argv[1]))
doms = os.environ["MAIL_DOMAINS"].split(",")
cfg["sending_domain"] = os.environ["PRIMARY"]
cfg["sending_domains"] = doms
cfg["sending_ip"] = os.environ["PUBLIC_IP"]
cfg["sending_subdomains"] = [f"mail.{os.environ['PRIMARY']}"]
cfg["profiles"] = [f"{s}@{d}" for d in doms for s in os.environ["SENDERS"].split(",")]
cfg["kumo"] = {"host": "127.0.0.1", "port": 2587, "user": "outbound",
               "password": os.environ["KUMO_AUTH_PASS"],
               "from_addr": os.environ["FIRST_PROFILE"], "use_tls": True, "timeout": 30}
cfg["gophish"] = {"base_url": "http://127.0.0.1:8333/api", "api_key": os.environ["GOPHISH_API_KEY"]}
json.dump(cfg, open("/opt/deliverability/config.json", "w"), indent=2)
print("deliverability config written")
PYEOF
chmod 600 "$DELIV/config.json"
(cd "$DELIV" && python3 cli.py precheck || true) | tail -15
log "deliverability CLI ready (precheck failures before DNS setup are expected)"
}

# ============================================================
# PHASE 9: dashboard (build + start, loopback service)
# ============================================================
log "PHASE 9: dashboard"
dry "npm ci + build + pm2 start (open mode, loopback :3001)" || {
# shellcheck disable=SC1090
. "$SECRETS_FILE"
rsync -a --delete --exclude .git --exclude node_modules --exclude .next \
  --exclude .data/ --exclude .env.local --exclude .env.vercel --exclude knowledge/ \
  --exclude "AI Venture/" --exclude efa-results.json --exclude efa-run.log \
  --exclude Efa.csv "$APP_SRC/" "$APPDST/"
cat > "$APPDST/.env.local" << ENVEOF
GOPHISH_API_URL=http://127.0.0.1:8333
GOPHISH_API_KEY=$GOPHISH_API_KEY
LEAD_JOB_API_URL=http://127.0.0.1:8091
LEAD_JOB_API_SECRET=$JOB_API_SECRET
REACHER_URL=http://127.0.0.1:8091
REACHER_SECRET=$REACHER_SECRET
NEXT_PUBLIC_APP_URL=https://$APP_HOST
DISABLE_AUTH=true
DISABLE_AUTH_USER_ID=owner
DISABLE_AUTH_USER_EMAIL=$FIRST_PROFILE
INTERNAL_API_SECRET=$INTERNAL_API_SECRET
VAULT_MASTER_KEY=$VAULT_MASTER_KEY
PORT=3001
ENVEOF
chmod 600 "$APPDST/.env.local"
cd "$APPDST" && npm ci --no-audit --no-fund
NEXT_PUBLIC_APP_URL="https://$APP_HOST" npm run build
pm2 start ecosystem.config.cjs > /dev/null 2>&1 || pm2 restart ecosystem.config.cjs > /dev/null 2>&1
pm2 save > /dev/null 2>&1 || true
for _ in $(seq 1 30); do (echo > /dev/tcp/127.0.0.1/3001) 2>/dev/null && break; sleep 2; done
(echo > /dev/tcp/127.0.0.1/3001) 2>/dev/null || die "dashboard never came up on :3001"
log "dashboard live on :3001 (open mode — see warnings at the end)"
}

# ============================================================
# PHASE 10: Caddy (public HTTPS for app/console/track/warmbly)
# ============================================================
log "PHASE 10: Caddy"
dry "write Caddyfile from template, validate, reload" || {
sed -e "s/__BASE__/$BASE_DOMAIN/g" -e "s/__APP__/$APP_HOST/g" \
    -e "s/__CONSOLE__/$CONSOLE_HOST/g" -e "s/__TRACK__/$TRACK_HOST/g" \
    -e "s/__WARM__/$WARM_HOST/g" -e "s/__WARM_API__/$WARM_API/g" \
    -e "s/__WARM_TRACK__/$WARM_TRACK/g" "$REPO/install/Caddyfile.tmpl" > /etc/caddy/Caddyfile
grep -q "__" /etc/caddy/Caddyfile && die "Caddyfile template placeholders left unfilled"
caddy validate --config /etc/caddy/Caddyfile > /dev/null || die "Caddyfile invalid"
systemctl reload caddy 2>/dev/null || systemctl restart caddy
sleep 6
for u in "https://$APP_HOST/" "https://$CONSOLE_HOST/login"; do
  code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 "$u" 2>&1 || echo 000)
  [ "$code" = 200 ] && log "  $u -> $code" || warn "$u -> $code (DNS/TLS may still be propagating)"
done
}

# ============================================================
# PHASE 11: lead verification (Reacher engine + job API)
# ============================================================
log "PHASE 11: lead verification"
dry "start reacher backend + job_api service" || {
# shellcheck disable=SC1090
. "$SECRETS_FILE"
mkdir -p "$REPO/reacher-state"
cp "$REPO/reacher/docker-compose.yml" "$SLIDEIN/reacher-compose.yml"
cd "$SLIDEIN" && docker compose -p slidein-reacher -f reacher-compose.yml up -d
mkdir -p "$REACH" "$REACH/data"
cp "$REPO/reacher/job_api/app.py" "$REPO/reacher/job_api/requirements.txt" "$REACH/"
[ -x "$REACH/.venv/bin/python" ] || python3 -m venv "$REACH/.venv"
"$REACH/.venv/bin/pip" install -q -r "$REACH/requirements.txt"
cat > "$REACH/.env" << REACHENV
JOB_API_SECRET=$JOB_API_SECRET
REACHER_SECRET=$REACHER_SECRET
REACHER_URL=http://127.0.0.1:8090
DATA_DIR=$REACH/data
REACHENV
chmod 600 "$REACH/.env"
cp "$REPO/reacher/reacher-jobapi.service" /etc/systemd/system/reacher-jobapi.service
systemctl daemon-reload && systemctl enable reacher-jobapi > /dev/null 2>&1 || true
systemctl restart reacher-jobapi
for _ in $(seq 1 30); do (echo > /dev/tcp/127.0.0.1/8090) 2>/dev/null && (echo > /dev/tcp/127.0.0.1/8091) 2>/dev/null && break; sleep 2; done
(echo > /dev/tcp/127.0.0.1/8091) 2>/dev/null || die "job_api never came up on :8091"
log "lead verification live (:8090 engine, :8091 job API)"
}

# ============================================================
# PHASE 12: Warmbly warmup platform (skipped with --minimal)
# ============================================================
if [ "$MINIMAL" = 1 ]; then
  log "PHASE 12: Warmbly skipped (--minimal)"
else
  log "PHASE 12: Warmbly"
  dry "deploy warmbly compose + env" || {
  mkdir -p "$WARMB"
  touch "$WARMB/.env" && chmod 600 "$WARMB/.env"
  for kv in "TRACKING_DOMAIN=$WARM_TRACK" "APP_URL=https://$WARM_HOST" \
            "API_PUBLIC_URL=https://$WARM_API" "CORS_ALLOW_ORIGINS=https://$WARM_HOST" \
            "WEBSOCKET_URL=wss://$WARM_API/socket/websocket"; do
    k="${kv%%=*}"; grep -q "^$k=" "$WARMB/.env" || echo "$kv" >> "$WARMB/.env"
  done
  bash "$REPO/warmbly/gen-warmbly-env.sh"
  cp "$REPO/warmbly/docker-compose.yml" "$WARMB/docker-compose.yml"
  # Warmbly's compose joins the kumo production net via its kumo-relay
  # alias (external name kumomta-production_production, created in Phase 6).
  (cd "$WARMB" && docker compose -p warmbly -f docker-compose.yml up -d)
  log "Warmbly deployed — connect mailboxes in the Warmbly UI (https://$WARM_HOST) as the final step"
  }
fi

# ============================================================
# PHASE 13: Agent-Reach research tooling (best effort)
# ============================================================
log "PHASE 13: Agent-Reach"
dry "pip install Agent-Reach from upstream" || {
pip3 install --break-system-packages -q "git+https://github.com/Panniantong/Agent-Reach.git" 2>&1 | tail -2 || warn "Agent-Reach install failed — research features degrade (rerun installer later)"
pip3 show agent-reach > /dev/null 2>&1 && log "Agent-Reach installed" || warn "Agent-Reach not importable — non-fatal"
}

# ============================================================
# PHASE 14: DNS records (print + save + verify loop)
# ============================================================
log "PHASE 14: DNS records"
DNS_FILE=$SLIDEIN/dns-records.txt
dry "print + verify DNS table" || {
{
echo "SlideIn DNS for $BASE_DOMAIN (server $PUBLIC_IP) — add at your DNS provider:"
echo ""
echo "[Website]  A  $BASE_DOMAIN  -> $PUBLIC_IP"
for h in "$APP_HOST" "$CONSOLE_HOST" "$TRACK_HOST"; do echo "[Website]  A  $h  -> $PUBLIC_IP"; done
if [ "$MINIMAL" = 0 ]; then
for h in "$WARM_HOST" "$WARM_API" "$WARM_TRACK"; do echo "[Website]  A  $h  -> $PUBLIC_IP"; done
fi
echo ""
for d in "${DOMAINS[@]}"; do
  PKEY=$(openssl rsa -in "$KUMO_LAB/dkim/$d.private.key" -pubout 2>/dev/null | grep -v -- "----" | tr -d '\n')
  echo "[$d]"
  echo "  TXT @ : v=spf1 ip4:$PUBLIC_IP mx -all   (MERGE with existing includes, e.g. Zoho/Google — never two SPF records)"
  echo "  TXT dkim._domainkey : v=DKIM1; k=rsa; p=$PKEY"
  echo "  TXT _dmarc : v=DMARC1; p=quarantine; rua=mailto:dmarc@$d"
  echo ""
done
echo "PTR (VPS host panel, not DNS): $PUBLIC_IP -> $MAIL_HOST"
echo "MX: your choice (Zoho/Google) for receiving — SlideIn only sends."
} | tee "$DNS_FILE"
chmod 600 "$DNS_FILE"
log "verify loop (informational until DNS propagates):"
for h in "$APP_HOST" "$CONSOLE_HOST"; do
  hit=""; for _ in $(seq 1 5); do hit=$(dig +short A "$h" 2>/dev/null | head -1); [ "$hit" = "$PUBLIC_IP" ] && break; sleep 10; done
  [ "$hit" = "$PUBLIC_IP" ] && log "  $h resolves here" || warn "$h not resolving yet — add DNS, then rerun installer to re-verify"
done
}

# ============================================================
# PHASE 15: summary
# ============================================================
echo ""
echo "================================================"
echo "  INSTALL COMPLETE"
echo "================================================"
echo ""
echo "Dashboard:  https://$APP_HOST/  (also https://$BASE_DOMAIN/)"
echo "  Instant local preview (before DNS): ssh -L 3001:localhost:3001 root@$PUBLIC_IP"
echo "  then open http://localhost:3001 in your browser."
echo "Console:    https://$CONSOLE_HOST/login  (user: admin — see temp password below)"
echo "Tracking:   https://$TRACK_HOST/  (404 on / is correct)"
[ "$MINIMAL" = 0 ] && echo "Warmbly:    https://$WARM_HOST/"
echo ""
echo "Sending profiles: $(echo "$MAIL_DOMAINS" | tr ',' ' ' | wc -w) domain(s) x $(echo "$SENDERS" | tr ',' ' ' | wc -w) sender(s) via KumoMTA :2587"
echo "Secrets:    $SECRETS_FILE (root-only, mode 600 — back it up)"
echo "DNS table:  $DNS_FILE"
echo ""
echo "FIRST LOGIN (GoPhish console):"
echo "  journalctl -u gophish | grep 'Please login' | tail -1"
echo "  Log in as admin, then change the password immediately."
echo ""
echo "NEXT STEPS:"
echo "  1. Add DNS from $DNS_FILE, wait ~5 min, rerun installer to re-verify"
echo "  2. Set PTR in your VPS panel: $PUBLIC_IP -> $MAIL_HOST"
echo "  3. Verify mail auth: cd /opt/deliverability && python3 cli.py precheck"
echo "  4. Register domains in Gmail Postmaster Tools + Microsoft SNDS"
echo "  5. Connect mailboxes in Warmbly UI; ramp volume gradually (cold IP)"
echo "  6. Rotate nothing now — all secrets were generated fresh"
echo ""
echo "WARNINGS:"
echo "  - Dashboard ships OPEN (no login) for first-run simplicity."
echo "    Put Caddy basic_auth in front of $APP_HOST before inviting users,"
echo "    or wire Appwrite/Supabase keys into $APPDST/.env.local + rebuild."
echo "  - Unsubscribe requests land in each sender mailbox — honor manually."
echo "  - This installer never sends email by itself. First sends are yours."

