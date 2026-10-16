# Client Instance Onboarding Playbook (Under 2-Hour SOP)

> **Audience:** Slidein Operators, Support Engineers, Coding Agents  
> **Goal:** Take a new client business from raw intake notes to an active, branded, verified instance in **under 2 hours** (typical runtime: 45–60 minutes).  
> **Standard:** Zero code forks. Pinned application release + validated configuration + isolated host.

---

## 1. Overview & Time Budget

| Phase | Duration | Responsible | Objective |
| :--- | :--- | :--- | :--- |
| **Stage 1: Intake & Config Generation** | 15 mins | Founder / Operator | Ingest client notes via Chat/IDE intake tool; compile `deployment_config.json`. |
| **Stage 2: Pre-Flight Validation** | 5 mins | Automated / Operator | Run 16-stage schema & policy check. Pass/Fail go/no-go gate. |
| **Stage 3: One-Tap VPS Provisioning** | 20 mins | Automated (`install.sh`) | Fresh Ubuntu 24.04 VPS booted; KumoMTA, Caddy, API, and Dashboard installed. |
| **Stage 4: DNS & Mail Verification** | 10 mins | Operator / Client DNS | Point A, SPF, DKIM, DMARC records. Verify with `deliverability precheck`. |
| **Stage 5: Config & Secret Sync** | 5 mins | Operator | Inject validated config, sync team owners, bind secret references. |
| **Stage 6: Synthetic Safe-Test & Launch** | 5 mins | Automated (`POST /factory/test`) | Dry-run end-to-end stage execution. Activate workspace. |
| **Total Target Time** | **~60 mins** | — | **Go-Live complete with 60 mins buffer remaining.** |

---

## 2. Stage 1: Business Intake (Plain-Text / Chat Prompt)

Whenever you sign a client, paste their raw business intake directly into the intake compiler (`scripts/compile_client_intake.py` or the chat box).

### Required Intake Attributes Checklist
* [ ] **Legal Business Name:** (e.g. `Apex Mortgage Solutions`)
* [ ] **Base Domain for Dashboard:** (e.g. `app.apexmortgage.com`)
* [ ] **Sending Mailbox Domains:** (e.g. `apexoutreach.com`, `apex-talk.com`)
* [ ] **Primary Brand Color & Logo URL:** Hex color (e.g. `#1e40af`) and HTTPS image link.
* [ ] **Physical Postal Address (CAN-SPAM mandatory):** Street, city, state, postal code.
* [ ] **Target Persona & Value Proposition:** 1–2 sentences on what they sell and who they help.
* [ ] **Team Members (Owners):** Full name, email, CRM ID (if applicable), and verified booking calendar link (e.g. Cal.com / Calendly URL).
* [ ] **Daily Volume Cap:** (Default: 50 messages/day per mailbox during warmup).

---

## 3. Stage 2: Automated Pre-Flight Validation

Run the intake compiler on the raw notes:
```bash
python3 scripts/compile_client_intake.py --input client_intake.txt --output config.json
```
The compiler emits a strictly validated configuration and verifies:
1. All URLs are valid HTTPS strings.
2. The physical postal address is present (CAN-SPAM invariant).
3. Every team member has an assigned, unique email and calendar link.
4. Primary brand color meets accessibility contrast guidelines.

---

## 4. Stage 3: One-Tap VPS Provisioning

1. Boot a fresh Ubuntu 24.04 LTS VPS (2 vCPU / 4GB RAM, e.g., Hetzner CPX21 or DigitalOcean Droplet).
2. SSH into the fresh VPS as root:
   ```bash
   ssh root@<TARGET_VPS_IP>
   ```
3. Run the one-command installer:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/sheikhmdnasrullah-dotcom/SlideIn/main/install.sh \
     | bash -s -- --base-domain <CLIENT_BASE_DOMAIN> \
                --mail-domains <CLIENT_MAIL_DOMAINS> \
                --admin-email admin@<CLIENT_BASE_DOMAIN> \
                --non-interactive
   ```
4. The installer automatically provisions:
   * **Caddy 2:** Auto-configured for HTTPS with Let's Encrypt.
   * **slidein-api:** Python FastAPI workflow engine on `:8100` supervised by systemd.
   * **slidein-app:** Branded Next.js client workspace on `:3000` supervised by PM2.
   * **KumoMTA:** High-performance MTA on loopback `:2587` with DKIM signing.
   * **Security Hardening:** UFW firewall (ports 22, 80, 443, 25 only).

---

## 5. Stage 4: DNS Configuration

Add the following DNS records to the client's DNS manager (Cloudflare, GoDaddy, Route53):

| Type | Name / Host | Target / Value | Purpose |
| :--- | :--- | :--- | :--- |
| **A** | `app.<base-domain>` | `<TARGET_VPS_IP>` | Client Workspace UI |
| **A** | `api.<base-domain>` | `<TARGET_VPS_IP>` | Client API Endpoint |
| **A** | `mail.<mail-domain>` | `<TARGET_VPS_IP>` | Mail Server Hostname |
| **TXT** | `@` (mail domain) | `v=spf1 ip4:<TARGET_VPS_IP> ~all` | SPF Authentication |
| **TXT** | `kumo._domainkey` | `<COPIED_FROM_/opt/slidein/.secrets.env>` | 2048-bit DKIM Key |
| **TXT** | `_dmarc` | `v=DMARC1; p=reject; rua=mailto:dmarc@...` | DMARC Enforcement |

**Verify DNS propagation:**
```bash
python3 /opt/deliverability/cli.py precheck --domain <CLIENT_MAIL_DOMAIN>
```
*Gate condition:* Must return **100% Green**. Do not proceed to sending until DKIM and SPF pass.

---

## 6. Stage 5: Unified Client Bootstrap & Synthetic Testing

Run the automated instance bootstrapper directly on the host (or pass `--config` during `install.sh`):

```bash
# Option A: From raw text intake notes
python3 scripts/bootstrap_client_instance.py --input client_intake.txt

# Option B: From pre-compiled JSON bundle
python3 scripts/bootstrap_client_instance.py --bundle client_bundle.json
```

This single command automatically:
1. Provisions the client workspace and database.
2. Ingests business profile, active offers, and ICP rules.
3. Configures versioned deployment configuration and dynamic branding.
4. Enforces CAN-SPAM compliance (explicit physical address and lawful basis).
5. Imports team owners with verified personal booking links.
6. Connects hybrid inboxes:
   - **Google Workspace / Microsoft 365:** Fast-start warm outreach.
   - **KumoMTA:** Dedicated VPS inboxes connected to Warmbly for gradual warmup.
7. Executes an end-to-end synthetic test (`mode=synthetic`), verifying discovery, qualification, owner routing, and personalization without network side-effects.
8. Evaluates all 16 pre-flight validation checkpoints.

---

## 7. Stage 6: Go-Live Operator Activation

Once the synthetic test passes and the validation gate is `READY`, activate live campaigns:

```bash
# Via CLI:
python3 scripts/pause_tenant.py --tenant-id <TENANT_ID> --resume

# Or directly during bootstrap:
python3 scripts/bootstrap_client_instance.py --bundle client_bundle.json --activate
```

---

## 8. Ongoing Instance Operations & Maintenance

### Health Check (All Ports, PM2, systemd, Caddy):
```bash
./scripts/health_check.sh <CLIENT_BASE_DOMAIN>
```

### One-Click Pause & Resume (Emergency / Vacation):
```bash
# Pause instance
./scripts/pause_tenant.py --tenant-id <TENANT_ID> --pause --reason "Client requested pause"

# Check status
./scripts/pause_tenant.py --tenant-id <TENANT_ID> --status

# Resume instance
./scripts/pause_tenant.py --tenant-id <TENANT_ID> --resume
```

### Automated Database & Secret Backup:
```bash
./scripts/backup_instance.sh
# Stores timestamped tar.gz in /opt/slidein/backups/ (retains last 7 copies)
```

---

## 9. Troubleshooting & Escalation Matrix

| Symptom | Root Cause | Remediation Path |
| :--- | :--- | :--- |
| **`booking_unverified` on test** | Team owner has invalid calendar URL or hasn't verified booking destination. | Check URL in `owners.json`. Ensure URL responds with HTTP 200 and set `booking_verified: true`. |
| **Caddy TLS issuance fails** | DNS A record has not propagated to the VPS IP yet. | Run `dig +short app.<domain>`. Ensure it returns the VPS IP. Then restart Caddy: `systemctl restart caddy`. |
| **Statutory gate blocks pre-send** | Missing physical postal address or lawful basis. | Edit policy: `PUT /v1/tenants/{id}/policy` with valid street address. |
| **Circuit breaker trips (>3% bounce)** | Dirty or unverified prospect email list. | Quarantine trips automatically. Run Reacher list verification before requesting admin resume via `POST /quarantine/resolve`. |
| **Cold IP deliverability warnings** | KumoMTA outbound sent before completing 2-3 week Warmbly warmup. | Route initial outreach through Google Workspace / M365 while KumoMTA ramps up in Warmbly. |

