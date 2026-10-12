# KumoMTA + DNS Setup Checklist

## VPS Setup (run on VPS as root)

```bash
# Copy and run this script
bash setup_kumomta.sh
```

**What the script does:**
1. Installs KumoMTA from official repository
2. Creates `/opt/kumomta/etc/policy/secrets.lua` with auth user `outbound` /
   password from `$KUMO_AUTH_PASS` (set in the deploy environment)
3. Generates DKIM key pair for `nasrullahtanim.me`
4. Copies production policy from `kumomta-lab/policy/init.lua`
5. Starts KumoMTA service
6. Verifies listener on `127.0.0.1:5872`
7. Tests SMTP AUTH

**After running the script, paste back:**
- The DKIM public key (starts with `v=DKIM1; k=rsa; p=`)
- Output of: `ss -tlnp | grep 5872`
- Output of: `/opt/kumomta/sbin/kumod --version`

## DNS Records to Add

Add these in your DNS provider (Cloudflare/Namecheap/etc):

| Type | Name | Value |
|------|------|-------|
| TXT | `kumo._domainkey.nasrullahtanim.me` | `v=DKIM1; k=rsa; p=<paste public key from script>` |
| TXT | `_dmarc.nasrullahtanim.me` | `v=DMARC1; p=quarantine; rua=mailto:dmarc@nasrullahtanim.me; adkim=s; aspf=s` |
| TXT | `nasrullahtanim.me` | `v=spf1 ip4:169.58.207.75 mx -all` |
| PTR | `169.58.207.75` | `mail.nasrullahtanim.me` (request from VPS host) |

**Verify with:**
```bash
python3 cli.py validate-dns nasrullahtanim.me 169.58.207.75
```

## Local Config (already updated)

`config.json` has been updated with:
- `kumo.user`: `outbound`
- `kumo.password`: value of `KUMO_AUTH_PASS` (local file only, never committed)
- `kumo.host`: `127.0.0.1`
- `kumo.port`: `5872`

## Send Test Email

Once KumoMTA is running and DNS is set:

```bash
cd deliverability

# 1. Verify system health
python3 cli.py precheck

# 2. Check placement risk
python3 cli.py placement-risk /tmp/test_send.eml

# 3. Run full gate check
python3 cli.py gate-check /tmp/test_send.eml

# 4. Run real seed test (requires IMAP app passwords)
python3 cli.py seed-test /tmp/test_send.eml

# 5. Send test email
python3 cli.py send /tmp/test_send.eml tanimsyt@gmail.com hello@nasrullahtanim.me
```

## Security Note

**Change these passwords immediately after testing:**
1. VPS root password: env `VPS_PASS` (local secret store only)
2. KumoMTA `outbound` password: env `KUMO_AUTH_PASS` (local secret store only)
