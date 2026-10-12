# Self-Hosting — SlideIn

> Designed path, not yet exercised end-to-end on a fresh host. Local
> operation is verified; treat first production bring-up as a rehearsal.

## Requirements

- Ubuntu 22.04/24.04 LTS, clean public IPv4, outbound TCP port 25 unblocked.
- PTR record: `<VPS_IP> -> mail.<domain>` (via host provider).
- Public DNS: SPF (`v=spf1 ip4:<VPS_IP> ~all`), DKIM TXT (2048-bit, selector
  `dkim`), DMARC (`v=DMARC1; p=reject; rua=mailto:dmarc@<domain>`).
- Valid TLS certificates (Let's Encrypt) for admin surfaces.

## Bring-up

```bash
# 1. Deploy (reads VPS_PASS / KUMO_AUTH_PASS / KUMO_ADMIN_PASS from env)
kumomta-lab/scripts/deploy-production.sh [user@host]

# 2. DNS records
deliverability/setup-dns.sh

# 3. Verify
cd /opt/deliverability && python3 cli.py precheck
python3 deliverability/configure-gophish-profiles.py

# 4. Warmup, then campaigns
cd /opt/warmup-engine && npm start
python3 /opt/deliverability/campaign_worker.py
```

The deploy script was path-fixed and statically verified 2026-10-12
(`bash -n` + all 19 source paths); it has never completed a live run.

## Differences from local development

| Capability | Local | Self-hosted |
|---|---|---|
| Egress | Forced Mailpit sink | Direct recipient MX |
| Port 25 | Not required | Mandatory open outbound |
| PTR / DNS | N/A | Mandatory, aligned |
| TLS | Self-signed/disabled | Valid certificates |
| DKIM keys | Lab keys | Per-domain 2048-bit, generated at deploy |

## Hardening notes

Keep admin ports off the public internet where possible (KumoMTA :8029,
GoPhish :8333, Grafana :3000 bind accordingly), rotate all credentials
after first deploy, and keep production `.env`/configs on the host only —
never in this repository.
