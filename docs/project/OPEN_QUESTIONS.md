# OPEN QUESTIONS & DECISIONS REGISTER

> **Status:** Living Register  
> **Last Updated:** 2026-10-16 (Owner Decisions Formally Recorded)  
> **Related Specifications:** [`../product/PROSPECT_ENGAGEMENT.md`](../product/PROSPECT_ENGAGEMENT.md), [`../architecture/ENGAGEMENT_ARCHITECTURE.md`](../architecture/ENGAGEMENT_ARCHITECTURE.md)  

---

## 1. Owner Decisions (Confirmed 2026-10-16)

| ID | Subject | Decision / Resolution | Status |
|---|---|---|---|
| **OQ-001** | Executive Delivery Report | Built and established at [`docs/operations/EXECUTIVE_DELIVERY_REPORT.md`](../operations/EXECUTIVE_DELIVERY_REPORT.md). | **RESOLVED** |
| **OQ-002** | Client Communications Register | Built and established at [`docs/product/CLIENT_COMMUNICATIONS_REGISTER.md`](../product/CLIENT_COMMUNICATIONS_REGISTER.md). | **RESOLVED** |
| **OQ-003** | Updated Brand Kit | Built and established at [`docs/design/UPDATED_BRAND_KIT.md`](../design/UPDATED_BRAND_KIT.md). | **RESOLVED** |
| **OQ-004** | Booking / Calendar Provider | **Primary Default:** Notion Booking Calendar. **Secondary:** Dedicated booking link sync (Cal.com, Calendly, or custom link). | **RESOLVED** |
| **OQ-005** | Milestone 1 (M1) Approval | **Approved** by the owner as the official first development milestone and MVP scope. | **RESOLVED** |
| **OQ-006** | Agent Autonomy & Grace Period | **24-Hour Business Grace Period:** When a reply arrives, notify via Email and Telegram/Discord summary. Client has 24 business hours (excluding US non-working days and federal holidays) to reply manually. If no manual reply occurs, the agent drafts and dispatches an authentic, indistinguishable response grounded in the knowledge base. | **RESOLVED** |
| **OQ-007** | First-Touch Link Policy | **Strict Prohibition:** NO links in cold first-touch outreach emails. Booking links and chat links are ONLY provided in the final stages when the prospect expresses interest or asks to speak with a representative. | **RESOLVED** |
| **OQ-020** | Inbound Email Path | **Dual Architecture Supported:**<br>1. **KumoMTA Outbound/Inbound:** Open-source webmail viewer integrated into dashboard.<br>2. **External Mailbox Sync:** Google Workspace & Microsoft 365 OAuth/IMAP sync so replies land directly in the client's native Gmail/Outlook inboxes. | **RESOLVED** |
| **OQ-021** | Notion Calendar Integration | Notion Calendar / Notion Database integration developed as the primary scheduling provider adapter. | **RESOLVED** |
| **OQ-023** | Notification Channels | Real-time alerts dispatched 24/7 via **Telegram Bot API**, **Discord Webhook**, and **Slack Webhook** in addition to email summaries. | **RESOLVED** |
| **OQ-046** | Pricing Authority | **Non-Negotiable Fixed Pricing:** Client sets fixed monthly pricing in the knowledge base. Agents have **ZERO discretion** to negotiate, discount, or modify pricing. | **RESOLVED** |

---

## 2. Active Technical & Implementation Items

| ID | Item | Priority | Assigned Milestone | Description |
|---|---|---|---|---|
| **OQ-022** | Pre-Send Approval Gate | P0 | Milestone 1 | Enforce `Message.ai_approved` check across all outbound dispatch queues. |
| **OQ-024** | LLM Grounding & Evals | P0 | Milestone 1 | Verify prompt guardrails preventing factual drift outside the tenant knowledge base. |
| **OQ-025** | Chat Hosting Domain | P1 | Milestone 2 | Finalize branded tenant subdomain routing for the hosted chat page. |
| **OQ-026** | Voice Provider Selection | P2 | Milestone 3 | Inbound/callback-only voice platform evaluation (Retell AI vs Synthflow) following legal review. |
| **OQ-041** | TCPA / Inbound Voice Review | P2 | Milestone 3 | Formal review of inbound voice greeting disclosure requirements prior to voice pilot. |
