#!/bin/bash
# Complete KumoMTA setup script for VPS
# Run this on: ssh root@169.58.207.75
set -e

echo "=== Step 1: Install KumoMTA ==="
mkdir -p /usr/share/keyrings
curl -fsSL https://dl.kumo.com/kumo-repo.asc | gpg --dearmor -o /usr/share/keyrings/kumo-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/kumo-archive-keyring.gpg] https://dl.kumo.com/apt stable main" > /etc/apt/sources.list.d/kumo.list
apt-get update
apt-get install -y kumomta

echo "=== Step 2: Create directories ==="
mkdir -p /opt/kumomta/etc/policy /etc/kumo/dkim /var/lib/kumo/spool/{data,meta} /var/log/kumo
chown -R kumod:kumod /etc/kumo/dkim /var/log/kumo /var/lib/kumo 2>/dev/null || true

echo "=== Step 3: Create KumoMTA secrets ==="
cat > /opt/kumomta/etc/policy/secrets.lua << EOF
return {
  users = {
    ['outbound'] = '${KUMO_AUTH_PASS:-local-dev-password}',
  },
}
EOF

echo "=== Step 4: Generate DKIM key ==="
openssl genrsa -out /etc/kumo/dkim/nasrullahtanim.me.private.key 2048
PUBLIC_KEY=$(openssl rsa -in /etc/kumo/dkim/nasrullahtanim.me.private.key -pubout -outform der | openssl base64 -A)
echo "============================================"
echo "DKIM PUBLIC KEY (add this to DNS):"
echo "v=DKIM1; k=rsa; p=$PUBLIC_KEY"
echo "============================================"
echo "$PUBLIC_KEY" > /etc/kumo/dkim/nasrullahtanim.me.public.txt

echo "=== Step 5: Copy production policy ==="
# Try common repo locations
if [ -f "/root/email-master raw/kumomta-lab/policy/init.lua" ]; then
  cp "/root/email-master raw/kumomta-lab/policy/init.lua" /opt/kumomta/etc/policy/init.lua
elif [ -f "/root/email-master/kumomta-lab/policy/init.lua" ]; then
  cp "/root/email-master/kumomta-lab/policy/init.lua" /opt/kumomta/etc/policy/init.lua
else
  echo "WARNING: Could not find init.lua. You need to copy it manually."
fi

echo "=== Step 6: Start KumoMTA ==="
systemctl enable --now kumomta
sleep 3
systemctl status kumomta --no-pager | head -15

echo "=== Step 7: Verify listener ==="
ss -tlnp | grep 5872 || echo "WARNING: KumoMTA not listening on 5872"

echo "=== Step 8: Test authentication ==="
python3 -c "
import smtplib
s = smtplib.SMTP('127.0.0.1', 5872, timeout=10)
try:
    s.ehlo()
    s.login('outbound', '${KUMO_AUTH_PASS:-local-dev-password}')
    print('AUTH: SUCCESS')
except Exception as e:
    print('AUTH: FAILED -', e)
finally:
    s.quit()
" 2>&1 || echo "Auth test failed - check credentials"

echo "=== Setup complete ==="
echo "Next steps:"
echo "1. Add DKIM TXT record: kumo._domainkey.nasrullahtanim.me"
echo "2. Add PTR record for 169.58.207.75 -> mail.nasrullahtanim.me"
echo "3. Update local config.json with kumo.user/password"
echo "4. Run: python3 cli.py send /tmp/test_send.eml tanimsyt@gmail.com hello@nasrullahtanim.me"
