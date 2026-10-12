#!/bin/bash
# ============================================================
# FIX DKIM SIGNING ON PRODUCTION SERVER
# Run this on: ssh root@169.58.207.75
# ============================================================
set -e

DOMAIN="nasrullahtanim.me"
SELECTOR="dkim"
DKIM_DIR="/etc/kumo/dkim"
POLICY_DIR="/opt/kumomta/etc/policy"

echo "=== Step 1: Check current DKIM config ==="
echo ""

# Check what selector KumoMTA is currently using
echo "Current policy DKIM signing:"
grep -n "selector" "$POLICY_DIR/init.lua" 2>/dev/null || echo "  No init.lua found!"
echo ""

# Check if private key exists
echo "Private keys in $DKIM_DIR:"
ls -la "$DKIM_DIR/" 2>/dev/null || echo "  No DKIM directory!"
echo ""

# Check what DNS expects
echo "DNS DKIM record selector: $SELECTOR"
echo "DNS DKIM record:"
dig +short "$SELECTOR._domainkey.$DOMAIN" TXT 2>/dev/null | head -1
echo ""

echo "=== Step 2: Generate new DKIM key (if needed) ==="
echo ""

# Always generate fresh key to ensure it matches DNS
mkdir -p "$DKIM_DIR"
openssl genrsa -out "$DKIM_DIR/$DOMAIN.private.key" 2048 2>/dev/null
chmod 600 "$DKIM_DIR/$DOMAIN.private.key"

# Extract public key
PUBLIC_KEY=$(openssl rsa -in "$DKIM_DIR/$DOMAIN.private.key" -pubout -outform der 2>/dev/null | openssl base64 -A)
echo "NEW DKIM PUBLIC KEY (you need to update DNS):"
echo "Selector: $SELECTOR"
echo "Record: v=DKIM1; k=rsa; p=$PUBLIC_KEY"
echo ""
echo "DNS record to update:"
echo "  $SELECTOR._domainkey.$DOMAIN"
echo "  v=DKIM1; k=rsa; p=$PUBLIC_KEY"
echo ""

echo "=== Step 3: Write production KumoMTA policy ==="
echo ""

cat > "$POLICY_DIR/init.lua" << 'POLICY_EOF'
-- KumoMTA Production Policy
-- DKIM signing with selector "dkim" for nasrullahtanim.me

local kumo = require 'kumo'

kumo.on('pre_init', function()
  kumo.set_httpinject_threads(math.ceil(kumo.available_parallelism() / 2))
  kumo.set_readyq_threads(math.ceil(kumo.available_parallelism() / 2))
end)

kumo.on('init', function()
  kumo.configure_accounting_db_path('/var/lib/kumo/accounting.db')

  kumo.define_spool { name = 'data', path = '/var/lib/kumo/spool/data', kind = 'RocksDB' }
  kumo.define_spool { name = 'meta', path = '/var/lib/kumo/spool/meta', kind = 'RocksDB' }

  kumo.start_esmtp_listener {
    listen = '0.0.0.0:5872',
    relay_hosts = { '127.0.0.1', '::1' },
    banner = 'nasrullahtanim.me ESMTP',
    max_messages_per_connection = 100,
    max_recipients_per_message = 50,
  }

  kumo.start_http_listener {
    listen = '0.0.0.0:8029',
    trusted_hosts = { '127.0.0.1', '::1' },
  }

  kumo.configure_local_logs {
    log_dir = '/var/log/kumo',
    max_segment_duration = '1s',
    back_pressure = 512 * 1024,
  }
end)

kumo.on('smtp_server_auth_plain', function(_authz, authc, password)
  local secrets = dofile '/opt/kumomta/etc/policy/secrets.lua'
  return secrets.users[authc] == password
end)

kumo.on('http_server_validate_auth_basic', function(user, password)
  local secrets = dofile '/opt/kumomta/etc/policy/secrets.lua'
  return secrets.users[user] == password
end)

-- DKIM signing: selector "dkim" for ALL outbound
kumo.on('smtp_server_message_received', function(msg)
  local from = msg:from_header()
  if not from then
    kumo.reject(552, '5.6.0 Missing From header')
  end

  local domain = from.domain
  local key_path = '/etc/kumo/dkim/' .. domain .. '.private.key'

  local ok, signer = pcall(function()
    return kumo.dkim.rsa_sha256_signer {
      domain = domain,
      selector = 'dkim',
      headers = { 'From', 'To', 'Subject', 'Date', 'Message-ID' },
      key = key_path,
    }
  end)

  if ok then
    msg:dkim_sign(signer)
  else
    kumo.log('DKIM sign failed: ' .. domain .. ' - ' .. tostring(signer))
  end
end)

kumo.on('http_message_generated', function(msg)
  local from = msg:from_header()
  if from then
    local domain = from.domain
    local key_path = '/etc/kumo/dkim/' .. domain .. '.private.key'

    local ok, signer = pcall(function()
      return kumo.dkim.rsa_sha256_signer {
        domain = domain,
        selector = 'dkim',
        headers = { 'From', 'To', 'Subject', 'Date', 'Message-ID' },
        key = key_path,
      }
    end)

    if ok then
      msg:dkim_sign(signer)
    end
  end
end)

kumo.on('get_egress_path_config', function(_routing_domain, _egress_source, _site_name)
  return kumo.make_egress_path {
    connection_limit = 50,
    max_ready = 5000,
    enable_tls = 'Opportunistic',
    enable_mta_sts = false,
    smtp_port = 25,
    max_message_rate = '100/min',
    max_connection_rate = '30/min',
    max_deliveries_per_connection = 50,
    refresh_strategy = 'Epoch',
  }
end)
POLICY_EOF

echo "  Written new policy to: $POLICY_DIR/init.lua"

echo ""
echo "=== Step 4: Restart KumoMTA ==="
echo ""

systemctl restart kumomta
sleep 3

if systemctl is-active --quiet kumomta; then
    echo "  KumoMTA restarted successfully"
else
    echo "  ERROR: KumoMTA failed to start!"
    journalctl -u kumomta --no-pager -n 20
    exit 1
fi

echo ""
echo "=== Step 5: Verify DKIM signing ==="
echo ""

# Send test email
python3 << 'PYEOF'
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
import time
import os

msg = MIMEText("DKIM verification test - check headers for DKIM-Signature")
msg["From"] = "hello@nasrullahtanim.me"
msg["To"] = "tanimsyt@gmail.com"
msg["Subject"] = f"DKIM Fix Test {int(time.time())}"
msg["Date"] = formatdate(localtime=False)
msg["Message-ID"] = f"<dkim-fix-{int(time.time())}@nasrullahtanim.me>"

try:
    s = smtplib.SMTP("127.0.0.1", 5872, timeout=10)
    s.ehlo()
    s.starttls()
    s.ehlo()
    s.login("outbound", os.environ.get("KUMO_AUTH_PASS", "local-dev-password"))
    s.sendmail("hello@nasrullahtanim.me", ["tanimsyt@gmail.com"], msg.as_string())
    print("  Test email sent!")
    s.quit()
except Exception as e:
    print(f"  ERROR: {e}")
PYEOF

echo ""
echo "=== DONE ==="
echo ""
echo "IMPORTANT: You need to update your DNS DKIM record!"
echo ""
echo "Current DNS record might have a DIFFERENT public key."
echo "New public key to put in DNS:"
echo "  Selector: $SELECTOR"
echo "  Host: $SELECTOR._domainkey.$DOMAIN"
echo "  Value: v=DKIM1; k=rsa; p=$PUBLIC_KEY"
echo ""
echo "After updating DNS, wait 5 minutes then test:"
echo "  python3 deliverability/cli.py validate-dns $DOMAIN"
echo "  python3 deliverability/cli.py tx-send --to tanimsyt@gmail.com --subject 'Test' --text 'Test' --html '<p>Test</p>'"
