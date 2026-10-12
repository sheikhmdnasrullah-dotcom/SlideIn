# Cold Email Deliverability Production Setup

## Quick Start

### 1. Deploy to VPS
```bash
cd /opt/email-master\ raw
VPS_PASS=<vps-root-password> KUMO_AUTH_PASS=<kumo-smtp-password> \
  ./kumomta-lab/scripts/deploy-production.sh
```

### 2. Configure DNS
Add these records in Cloudflare for each domain:
- **SPF**: `v=spf1 ip4:169.58.207.75 mx -all`
- **DKIM**: `v=DKIM1; k=rsa; p=<public_key>` (see deploy output)
- **DMARC**: `v=DMARC1; p=quarantine; rua=mailto:dmarc@<domain>; adkim=s; aspf=s`
- **PTR**: `169.58.207.75 → mail.nasrullahtanim.me` (from host)

### 3. Verify
```bash
cd deliverability
python3 precheck.py          # Full pre-flight check
python3 cli.py seed-test     # Verify seed placement
```

### 4. Configure GoPhish
```bash
python3 configure-gophish-profiles.py
```

### 5. Start Warmup Engine
```bash
cd warmup-engine
npm start
```

### 6. Start Campaigns
```bash
python3 campaign_worker.py
```

## Architecture

```
GoPhish (8080/8333) → KumoMTA (2587) → Internet Recipients
                    ↕                    ↕
              GoPhish DB         DKIM/SPF/DMARC
              Prometheus         mailcow (IMAP)
              Grafana            Warmup Engine
              Alertmanager
```

## Sender Profiles

| Profile | Email | GoPhish ID |
|---------|-------|------------|
| hello | hello@nasrullahtanim.me | 9 |
| talk | talk@nasrullahtanim.me | 10 |
| connect | connect@nasrullahtanim.me | 11 |

## Key Files

- `kumomta-lab/policy/production_init.lua` - KumoMTA production policy
- `kumomta-lab/compose/docker-compose.production.yml` - Production Docker compose
- `deliverability/config.json` - Deliverability configuration
- `deliverability/GOPHISH_KUMOMTA_COORDINATION_PRODUCTION.md` - Full coordination guide
- `warmup-engine/config.json` - Warmup engine configuration
- `kumomta-lab/scripts/deploy-production.sh` - Deployment script
- `deliverability/setup-dns.sh` - DNS configuration script
- `deliverability/precheck.py` - Pre-flight verification

## Monitoring

- **Grafana**: http://169.58.207.75:3000 (admin/admin)
- **Prometheus**: http://169.58.207.75:9090
- **KumoMTA**: http://169.58.207.75:8029
- **GoPhish**: http://169.58.207.75:8333
- **Alerts**: Configured for bounce rate, DKIM failures, placement drops

## Warmup Schedule

| Period | Daily Sends | Step |
|--------|------------|------|
| Days 1-3 | 20 | Ramp up |
| Days 4-7 | 40 | Increase |
| Days 8-14 | 80 | Scale |
| Days 15-30 | 200 | Ramp |
| Day 30+ | Up to 500 | Steady |

## Security

- All SMTP requires AUTH (`outbound` / `$KUMO_AUTH_PASS`)
- DKIM signs every message
- Rate limits enforced per provider
- No open relay
- Lab mode removed for production
- FCrDNS verified
- IP not on any blacklists

## Troubleshooting

| Issue | Solution |
|-------|----------|
| KumoMTA down | `docker ps`, restart with `docker compose up -d` |
| DKIM failing | Verify DNS record matches private key |
| Low placement | Check warmup status, seed test |
| High bounces | Reduce rate, check recipient list |
| GoPhish config | Re-run `configure-gophish-profiles.py` |
