#!/bin/bash
# Fix KumoMTA DKIM signing for nasrullahtanim.me
# This script fixes the DKIM selector mismatch that causes emails to land in spam
set -e

DOMAIN="nasrullahtanim.me"
SELECTOR="dkim"
DKIM_DIR="/etc/kumo/dkim"
POLICY_DIR="/opt/kumomta/etc/policy"

echo "=== Fixing KumoMTA DKIM Configuration ==="
echo "Domain: $DOMAIN"
echo "Selector: $SELECTOR"
echo ""

# Step 1: Check if private key exists
echo "Step 1: Checking DKIM private key..."
if [ ! -f "$DKIM_DIR/$DOMAIN.private.key" ]; then
    echo "  Private key not found. Generating new DKIM key pair..."
    mkdir -p "$DKIM_DIR"
    openssl genrsa -out "$DKIM_DIR/$DOMAIN.private.key" 2048 2>/dev/null
    echo "  Generated new private key: $DKIM_DIR/$DOMAIN.private.key"
else
    echo "  Private key exists: $DKIM_DIR/$DOMAIN.private.key"
fi

# Step 2: Extract public key
echo ""
echo "Step 2: Extracting public key..."
PUBLIC_KEY=$(openssl rsa -in "$DKIM_DIR/$DOMAIN.private.key" -pubout -outform der 2>/dev/null | openssl base64 -A)
echo "  Public key: v=DKIM1; k=rsa; p=$PUBLIC_KEY"
echo ""
echo "  IMPORTANT: Verify this matches your DNS record!"
echo "  DNS record should be at: $SELECTOR._domainkey.$DOMAIN"
echo ""

# Step 3: Create proper production policy
echo "Step 3: Creating production policy..."
cat > "$POLICY_DIR/init.lua" << 'POLICY_EOF'
-- KumoMTA Production Policy for nasrullahtanim.me
-- Signs DKIM with selector "dkim" and routes to real MX servers

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
    kumo.log('WARNING: DKIM signing failed for ' .. domain .. ': ' .. tostring(signer))
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
    else
      kumo.log('WARNING: DKIM signing failed for ' .. domain .. ': ' .. tostring(signer))
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

echo "  Written production policy to: $POLICY_DIR/init.lua"

# Step 4: Fix file permissions
echo ""
echo "Step 4: Fixing permissions..."
chmod 600 "$DKIM_DIR/$DOMAIN.private.key"
chown -R kumod:kumod "$DKIM_DIR" 2>/dev/null || true
chown -R kumod:kumod "$POLICY_DIR" 2>/dev/null || true

# Step 5: Restart KumoMTA
echo ""
echo "Step 5: Restarting KumoMTA..."
systemctl restart kumomta
sleep 3

# Step 6: Verify
echo ""
echo "Step 6: Verifying..."
if systemctl is-active --quiet kumomta; then
    echo "  KumoMTA is running"
else
    echo "  ERROR: KumoMTA failed to start!"
    journalctl -u kumomta --no-pager -n 20
    exit 1
fi

# Step 7: Test DKIM signing
echo ""
echo "Step 7: Testing DKIM signing..."
python3 << 'PYEOF'
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate

msg = MIMEText("DKIM test")
msg["From"] = "hello@nasrullahtanim.me"
msg["To"] = "test@gmail.com"
msg["Subject"] = "DKIM Signing Test"
msg["Date"] = formatdate(localtime=False)

try:
    s = smtplib.SMTP("127.0.0.1", 5872, timeout=10)
    s.ehlo()
    s.starttls()
    s.ehlo()
    s.login("outbound", os.environ.get("KUMO_AUTH_PASS", "local-dev-password"))
    s.sendmail("hello@nasrullahtanim.me", ["test@gmail.com"], msg.as_string())
    print("  Test email sent successfully")
    s.quit()
except Exception as e:
    print(f"  ERROR: {e}")
PYEOF

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Verify DKIM DNS record matches the public key above"
echo "2. Check Gmail inbox/spam for the test email"
echo "3. Run: python3 cli.py validate-dns nasrullahtanim.me"
