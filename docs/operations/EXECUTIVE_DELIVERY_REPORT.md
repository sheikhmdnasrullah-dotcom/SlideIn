# SLIDEIN — EXECUTIVE DELIVERY REPORT

> **Document Class:** Authoritative Project Status & Delivery Report  
> **Target Audience:** Owner, Stakeholders, Engineering Agents  
> **System Scope:** Unified Agentic Acquisition OS, Production Deliverability Engine & Autonomous Engagement Platform  
> **Date:** 2026-10-16  
> **Owner:** Nasrullah Tanim  

---

## 1. Executive Summary

SlideIn combines **prospect discovery, company intelligence dossiers, 1:1 hyper-personalized outreach, dedicated MTA deliverability shielding, and conversational meeting booking** into one multi-tenant system.

This report establishes the baseline of verified production infrastructure, operational components, recent architectural upgrades, and the newly approved **Milestone 1 (Reply-to-Meeting Loop)** engagement roadmap.

---

## 2. Infrastructure & Production Status (`169.58.206.20`)

The production infrastructure is live and operational on Ubuntu LTS with Caddy edge routing, Docker runtime, and systemd service supervision:

| Component | Port / Interface | Status | Operational Details |
|---|---|---|---|
| **KumoMTA Engine** | `:2587` (SMTP AUTH), `:8029` (Admin API) | **Live & Verified** | Custom Lua production policy (`kumomta-lab/policy/production_init.lua`). 2048-bit DKIM signing active for `nasrullahtanim.me`, `tanim.social`, `tanim.tech`. Rate limits enforced per provider. |
| **GoPhish Campaign Manager** | `:8333` (Loopback) | **Live & Verified** | 9 authenticated sending profiles across active domains (`hello@`, `talk@`, `connect@`). Systemd supervised. |
| **Reacher Verification Engine** | `:8090` (Engine), `:8091` (FastAPI Job API) | **Live & Verified** | Full SMTP handshake verification (`RCPT TO`). Isolates safe, risky (catch-all), and invalid emails prior to dispatch. |
| **Warmbly Warmup Network** | 11 Docker Containers | **Live & Verified** | Automated warmup network governing deliverability ramps. |
| **Caddy Reverse Proxy** | `:80`, `:443` (Automatic Let's Encrypt) | **Live & Verified** | Secures `app`, `console`, `track`, and warmup endpoints. Binds internal services strictly to loopback. |
| **Next.js Command Hub (`workspace-app`)** | `http://localhost:3001` (Dev) / `:3001` (Prod PM2) | **Live & Verified** | Next.js 16 + React 19 console with SlideIn Venture design system parity, Fraunces display typography, and blueprint styling. |

---

## 3. Core Architectural Decisions & Invariants

1. **Platform Learning vs. Tenant Isolation:**
   - **Tenant Ephemeral Context:** Prospect dossiers, lead lists, company positioning, and email transcripts are strictly isolated by `tenant_id`. Zero cross-tenant data bleed.
   - **Platform Heuristic Genome:** Cross-tenant learning is limited to anonymized statistical models (send-time histograms, subject line lengths, deliverability bounce signatures). No PII or proprietary copy is ever promoted.
2. **Deliverability Shielding:**
   - Automated circuit breakers trigger an immediate pause if bounce rate exceeds **3.0%** or spam complaints exceed **0.05%**.
   - Cold outreach is strictly plain-text with zero commercial banners, zero tracking redirects, and zero links on first-touch outreach.
3. **Approved Milestone 1 (Reply-to-Meeting Loop):**
   - The owner has officially approved M1 as the primary development milestone.
   - Introduces dual-inbox routing (KumoMTA webmail vs Google/M365 sync), 24/7 background Telegram/Discord alerts, Notion Calendar scheduling, and a 24-hour smart escalation window.

---

## 4. Multi-Tenant Packaging & Commercial Architecture

| Plan Tier | Price | Infrastructure Allocation | Feature Set |
|---|---|---|---|
| **Free / Open-Core** | $0 (Self-Hosted) | User's own local machine / VPS | Open-source CLI, basic discovery, local SQLite store, manual dispatch. |
| **Cloud Managed** | **$350 / month** | Dedicated VPS slice (`169.58.206.20`), dedicated IP, warmed domains | Managed KumoMTA, Warmbly warmup, Reacher verification, 24/7 Telegram/Discord notifications, Notion booking sync, 24-hr agent fallback. |
| **Enterprise Fleet** | Custom ($750+) | Multi-domain cluster, dedicated IP pool | Multi-mission orchestrations, white-label client portals, custom CRM webhooks. |

---

## 5. Risk Assessment & Operational Governance

- **Mailbox Ingestion Gap (Resolved):** Inbound email path is architected with dual options: (a) KumoMTA MX routing to an open-source webmail dashboard viewer, and (b) native Google Workspace / Microsoft 365 IMAP/OAuth sync.
- **Agent Autonomy Guardrails:** Agents have zero authority to negotiate prices (fixed monthly pricing strictly enforced) and operate under a 24-hour human grace period.
