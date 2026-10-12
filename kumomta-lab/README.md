> **Note (2026-09-08):** the compliance framing in this README and in `docs/` (MASTER_PROMPT_COMPLIANT.md, PRODUCTION_RUNBOOK.md) predates the policy rewrite. The only working policy for the repo is now `PROJECT_POLICY.md` at the repo root; treat the docs below as historical reference for the lab design.


## Layout
```
kumomta/            KumoMTA image (built from source, pinned commit), entrypoint, forced resolver
kumomta-lab/
  compose/          docker-compose.yml (kumo + sink + redis + prom + grafana + alertmanager + loki)
  policy/           init.lua (Kumo policy), sink-scenarios.yaml, provider-shaping.toml
  dkim/             lab DKIM key pair (gitignored in practice; regen with openssl)
  monitoring/       prometheus / alerts / alertmanager / loki / grafana provisioning + dashboard
  scripts/          audit / deploy / rollback / backup / restore / healthcheck / test-*
  docs/             MASTER_PROMPT_COMPLIANT.md
sink-mx/            asyncio SMTP sink with scenario-driven responses + Prometheus metrics
deliverability/     existing compliance gate + circuit breaker + Kumo transport adapter
```

## Run the lab (needs Docker)
```bash
cd kumomta-lab/compose
docker compose build
docker compose up -d
# Kumo submission 127.0.0.1:2587 (user lab / password $KUMO_LAB_PASSWORD or lab-secret)
# Grafana 127.0.0.1:3000 (admin pw in secrets/grafana_admin.txt)
```

## Test it
```bash
bash kumomta-lab/scripts/healthcheck.sh
python3 kumomta-lab/scripts/send-test.py            # one msg per scenario
python3 kumomta-lab/scripts/send-test.py yahoo-tempfail   # just one
```

## Integration with the compliance pipeline
`deliverability/core/pipeline.py` is the ONLY approved outbound path. Set
`config["transport"] = "kumo"` and `config["kumo"] = {host, port, user, password,
from_addr}` so production mail goes KumoMTA -> (sink in lab / real MX in prod).
The gate still requires analyzer grade ≥ B AND 100% seed Inbox before any send.

## Production (VPS) — gated, non-disruptive
1. `ssh root@vps 'bash -s' < kumomta-lab/scripts/audit.sh` — READ-ONLY audit only.
2. `backup.sh` Mailcow + Kumo config; verify.
3. Validate SPF/DKIM/DMARC/PTR (`test-dns.sh`), TLS, EHLO.
4. Compliance gate + circuit breaker must pass before any external send.
5. Mailcow keeps inbound (port 25); Kumo handles outbound. Never an open relay.

## Known limitations / next steps (require live resources)
- Live VPS audit + Mailcow integration not executed here (no Docker/SSH egress).
- Real seed inboxes (Gmail/Outlook/Yahoo/iCloud) needed for true placement scoring.
- Per-provider *Kumo* shaping (beyond sink-side simulation) via a custom in-network
  resolver keyed by recipient domain (see NOTES in init.lua).
- Adaptive TSA warm-up engine on top of the gate/breaker.
