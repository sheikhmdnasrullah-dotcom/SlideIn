# GoPhish + KumoMTA Coordination Guide

## Architecture

```
┌─────────────────┐      ┌──────────────────────┐      ┌─────────────────┐
│   GoPhish       │      │   KumoMTA            │      │   Recipients    │
│   (Campaign     │─────▶│   (SMTP Relay)       │─────▶│   (Gmail,       │
│    Engine)      │      │   mail.              │      │    Yahoo,       │
│                 │      │   nasrullahtanim.me  │      │    Outlook)     │
└─────────────────┘      └──────────────────────┘      └─────────────────┘
       │                        │                          │
       │  GoPhish Profiles:     │  DKIM Signing            │  DMARC
       │  9: hello@            │  Selector: dkim          │  Policy:
       │  10: talk@            │  Domain: nasrullahtanim  │    quarantine
       │  11: connect@         │  Source: 169.58.207.75   │
       │                        │                          │
       │  Warmup Engine        │  Rate Limiting           │  Seed Tests
       │  (reputation)         │  (per-provider)          │  (placement)
       │                        │                          │
       │  Monitoring          │  Prometheus/Grafana      │
       └──────────────────────┘                          │
                                                         │
                                              ┌──────────┘
                                              │
                                     ┌─────────────────┐
                                     │  mailcow        │
                                     │  (IMAP/Local)   │
                                     │  Port 993/143   │
                                     └─────────────────┘
```

## Sender Profiles (3 from nasrullahtanim.me)

| Profile    | Email                      | Purpose           | GoPhish ID |
|------------|----------------------------|-------------------|------------|
| hello      | hello@nasrullahtanim.me   | Initial contact   | 9          |
| talk       | talk@nasrullahtanim.me    | Follow-up         | 10         |
| connect    | connect@nasrullahtanim.me | Relationship      | 11         |

## KumoMTA Configuration

- **Listen**: `0.0.0.0:2587` (SMTP submission, AUTH required)
- **Admin API**: `0.0.0.0:8029` (metrics, health)
- **DKIM**: Selector `dkim`, domains: `nasrullahtanim.me`, `tanim.social`, `tanim.tech`
- **Egress**: Provider-shaping with TLS opportunistic
- **Rate limits**: Per-provider (Gmail: 20/min, Yahoo: 15/min, etc.)

## GoPhish Configuration

- **Admin**: `https://email.tanim.tech` (or `http://169.58.207.75:8333`)
- **Phish Server**: `http://169.58.207.75:8080`
- **SMTP Relay**: `<VPS_IP>:2587` (auth: `outbound` / `$KUMO_AUTH_PASS`)
- **TLS**: Enabled for SMTP relay
- **Send Delay**: 5 seconds between sends

## Warm-up Sequence

1. **Days 1-3**: 20 emails/day to seed accounts (Gmail)
2. **Days 4-7**: 40 emails/day, add 2 more seed accounts
3. **Days 8-14**: 80 emails/day
4. **Days 15-30**: Ramp to 200/day
5. **After 30 days**: Up to 500/day with monitoring

## Campaign Workflow

1. **Pre-flight**: `python3 precheck.py` - Verify all infrastructure
2. **Seed test**: Send to seed accounts, verify inbox placement
3. **Gate check**: Content analysis + seed placement ≥ 80%
4. **Campaign send**: GoPhish → KumoMTA → Recipients
5. **Monitor**: Watch placement via Grafana + seed IMAP checks
6. **Adjust**: If placement < 80%, pause and investigate

## Security Rules

- All messages must pass through KumoMTA (no direct SMTP)
- DKIM must sign every message
- SPF must pass for sending IP
- DMARC must align (From domain = DKIM domain)
- No header forgery or spoofing
- Rate limits respected per provider
- Warmup engine governs volume ramping

## Monitoring

- **Grafana**: `http://169.58.207.75:3000` (admin/admin)
- **Prometheus**: `http://169.58.207.75:9090`
- **KumoMTA Admin**: `http://169.58.207.75:8029/metrics`
- **Alerts**: Configured for bounce rate, DKIM failures, placement drops

## DNS Records Required

All 3 domains (nasrullahtanim.me, tanim.social, tanim.tech):
- SPF: `v=spf1 ip4:169.58.207.75 mx -all`
- DKIM: `v=DKIM1; k=rsa; p=<public_key>`
- DMARC: `v=DMARC1; p=quarantine; rua=mailto:dmarc@<domain>; adkim=s; aspf=s`
- PTR: `169.58.207.75 → mail.nasrullahtanim.me`
- FCrDNS: `mail.nasrullahtanim.me ↔ 169.58.207.75`

## Deployment

```bash
# 1. Deploy to VPS
VPS_PASS=<vps-root-password> KUMO_AUTH_PASS=<kumo-smtp-password> \
  ./kumomta-lab/scripts/deploy-production.sh

# 2. Configure DNS (add records in Cloudflare)
bash deliverability/setup-dns.sh

# 3. Verify infrastructure
cd deliverability && python3 cli.py precheck

# 4. Configure GoPhish profiles
python3 deliverability/configure-gophish-profiles.py

# 5. Start warmup engine
cd warmup-engine && npm start

# 6. Start campaign worker
python3 campaign_worker.py
```

## Troubleshooting

| Issue | Check |
|-------|-------|
| Emails going to spam | Seed placement < 80%, check warmup status |
| KumoMTA not responding | `docker ps | grep kumomta`, check port 2587 |
| DKIM failing | Verify DNS DKIM record matches private key |
| SPF failing | Check `v=spf1 ip4:169.58.207.75 mx -all` DNS record |
| DMARC failing | Ensure From domain = DKIM domain |
| FCrDNS mismatch | Verify PTR record matches mail.nasrullahtanim.me |
| GoPhish not sending | Check GoPhish profiles point to KumoMTA:2587 |
| High bounce rate | Check recipient list quality, warmup status |
| High deferral rate | Reduce sending rate, check provider limits |
