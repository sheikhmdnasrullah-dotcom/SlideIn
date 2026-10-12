# SLIDEIN DEPLOYMENT, BACKUP & DISASTER RECOVERY

> **Production Deployment, Snapshot Backups & Failure Recovery**  
> Status: Authoritative Operational Guide  
> Version: 1.0.0

---

## 1. Production Topology

- **Primary VPS:** `169.58.207.75` (Ubuntu Linux)
  - **KumoMTA:** Port 2587 (authenticated SMTP submission), Port 8029 (Admin API)
  - **GoPhish Admin:** Port 8333
  - **Mailcow Mail Server:** Inbound MX and mailbox management
  - **Deliverability Service:** Port 8088
- **Operational Console (`workspace-app`):** Deployed via PM2 / Node service on port 3001 behind Caddy reverse proxy (`workspace.slideinventure.com`), with secondary deployment on Vercel.
- **Domains & Identities:**
  - `nasrullahtanim.me` (hello@, talk@, connect@)
  - `tanim.tech`
  - `tanim.social`

---

## 2. Production Deployment Procedure

1. **Environment Variables:** Ensure `VPS_PASS`, `KUMO_AUTH_PASS`, and `SLIDEIN_API_KEY` are present in local environment (values loaded from secure `deliverability/config.json`, never committed).
2. **Execute Deployment Script:**
   ```bash
   bash kumomta-lab/scripts/deploy-production.sh
   ```
3. **DNS Authentication Verification:**
   ```bash
   bash deliverability/setup-dns.sh
   python3 deliverability/precheck.py
   ```
4. **Configure Sending Profiles:**
   ```bash
   python3 deliverability/configure-gophish-profiles.py
   ```
5. **Start Warmup & Campaign Daemons:**
   ```bash
   cd warmup-engine && npm start
   python3 deliverability/campaign_worker.py
   ```

---

## 3. Backup & Snapshot Schedule

- **Deliverability & Suppression DB:**
  - Daily snapshot of `deliverability_state.db` and `gophish.db` created via SQLite `.backup` command to encrypted local off-site storage.
- **Postgres Database:**
  - Hourly automated WAL archiving and daily full `pg_dump` with 30-day retention.
- **Configuration & Policies:**
  - KumoMTA Lua policies (`production_init.lua`) and DNS records version-controlled in repository.

---

## 4. Disaster Recovery Runbooks

### Runbook A: MTA Process Failure / Socket Unresponsive
1. SSH into VPS: `ssh root@169.58.207.75`
2. Check container status: `docker ps -a | grep kumomta`
3. Inspect logs: `docker logs --tail 100 kumomta`
4. Restart service: `docker compose -f kumomta-lab/compose/docker-compose.production.yml restart kumomta`
5. Verify port 2587 connectivity: `nc -zv 127.0.0.1 2587`

### Runbook B: High Bounce / IP Reputation Degradation
1. Verify circuit breaker engaged: check `deliverability/deliverability_state.db` circuit state.
2. Halt active campaigns: `python3 deliverability/cli.py pause-all-campaigns`
3. Inspect bounce logs: `python3 deliverability/cli.py show-recent-bounces --limit 50`
4. Run lead scrub on affected list; purge unverifiable emails.
5. Ramp volume down to warmup tier ($10/\text{day}$) before resuming.
