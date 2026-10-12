# SLIDEIN API CONTRACTS & INTERFACE SPECIFICATIONS

> **REST API Endpoints, Request/Response Payloads, and Error Envelopes**  
> Status: Authoritative Contract  
> Version: 1.0.0

---

## 1. Global Conventions

- **Base Path:** `/api` (or `/v1`)
- **Headers:**
  - `Content-Type: application/json`
  - `X-Slidein-Tenant-ID: <tenant_id>` (Required for operator calls; inferred from session in user context)
- **Standard Error Envelope:**
```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Missing required fields for offer creation",
    "status": 400,
    "details": { "field": "target_persona" }
  }
}
```

---

## 2. Business Knowledge & Readiness Endpoints

### `POST /api/tenants/{tenant_id}/knowledge/profile`
Creates or updates the core business identity.
```json
// Request
{
  "legal_name": "Apex Cloud Systems",
  "website_url": "https://apexcloud.io",
  "industry": "Cloud Infrastructure",
  "company_description": "Automated multi-cloud cost optimization and FinOps tooling.",
  "core_value_prop": "Reduce AWS and Azure bills by 30% through automated rightsizing without downtime.",
  "markets_served": ["North America", "EMEA"]
}

// Response: 200 OK
{
  "status": "success",
  "profile_id": "prof_01J...",
  "updated_at": "2026-10-13T04:00:00Z"
}
```

### `POST /api/tenants/{tenant_id}/knowledge/offers`
Registers a specific business offer.
```json
// Request
{
  "name": "FinOps Audit & Automated Rightsizing",
  "summary": "14-day zero-risk audit that identifies unattached EBS volumes and oversized EC2 instances.",
  "pain_points_solved": ["Runaway AWS bills", "Lack of engineering time for infrastructure cleanup"],
  "target_persona": "VP of Engineering, CTO, Head of Infrastructure",
  "proof_points": ["Saved FinTech Corp $420k/yr", "SOC2 Type II certified"]
}

// Response: 201 Created
{
  "offer_id": "off_01J...",
  "is_active": true
}
```

### `GET /api/tenants/{tenant_id}/readiness`
Computes deployment operational readiness score.
```json
// Response: 200 OK
{
  "tenant_id": "ten_01J...",
  "overall_score": 92,
  "is_ready_for_activation": true,
  "checklist": [
    { "key": "business_profile", "status": "pass", "weight": 10 },
    { "key": "active_offers", "status": "pass", "weight": 15 },
    { "key": "icp_rules", "status": "pass", "weight": 15 },
    { "key": "sending_identity_dns", "status": "pass", "weight": 20 },
    { "key": "suppression_list", "status": "pass", "weight": 10 },
    { "key": "circuit_breaker", "status": "pass", "weight": 10 },
    { "key": "approval_policy", "status": "pass", "weight": 10 },
    { "key": "rate_limits", "status": "warn", "weight": 10, "message": "Hourly limit set to 25/hr" }
  ]
}
```

---

## 3. Prospecting & Qualification Endpoints

### `POST /api/tenants/{tenant_id}/prospects/import`
Batch CSV ingestion with deduplication.
```json
// Request
{
  "source": "csv_import",
  "records": [
    {
      "first_name": "Marcus",
      "last_name": "Vance",
      "email": "marcus@cloudwave.tech",
      "company_name": "CloudWave Technologies",
      "job_title": "VP Engineering",
      "company_domain": "cloudwave.tech"
    }
  ]
}

// Response: 200 OK
{
  "imported_count": 1,
  "duplicate_count": 0,
  "prospect_ids": ["prosp_01J..."]
}
```

### `POST /api/tenants/{tenant_id}/prospects/{prospect_id}/research`
Triggers targeted business research and evidence extraction.
```json
// Response: 202 Accepted
{
  "task_id": "task_res_01J...",
  "status": "processing"
}
```

### `GET /api/tenants/{tenant_id}/prospects/{prospect_id}/evidence`
Retrieves sourced research evidence.
```json
// Response: 200 OK
{
  "prospect_id": "prosp_01J...",
  "evidence": [
    {
      "id": "ev_01J...",
      "evidence_type": "hiring_signal",
      "claim_text": "CloudWave posted 4 job openings for Kubernetes and Cloud Cost Engineers last week.",
      "source_url": "https://careers.cloudwave.tech/jobs/7821",
      "confidence": 0.95,
      "verification_status": "verified"
    }
  ],
  "qualification": {
    "score": 94,
    "is_qualified": true,
    "explanation": "Matches ICP: Cloud infrastructure company with >50 employees, currently scaling DevOps."
  }
}
```

---

## 4. Drafting & Controlled Sending Endpoints

### `POST /api/tenants/{tenant_id}/drafts/generate`
Generates an evidence-grounded personalized message draft.
```json
// Request
{
  "prospect_id": "prosp_01J...",
  "offer_id": "off_01J..."
}

// Response: 200 OK
{
  "draft_id": "draft_01J...",
  "subject": "Quick question regarding Kubernetes scaling at CloudWave",
  "body": "Hi Marcus,\n\nSaw your team is hiring Cloud Cost Engineers to scale Kubernetes at CloudWave. We built an automated FinOps tool that helped FinTech Corp eliminate $420k/yr in idle cloud spend without engineering lift.\n\nWorth a 5-minute look?",
  "attributed_evidence_ids": ["ev_01J..."],
  "deliverability_score": 96,
  "status": "pending_review"
}
```

### `POST /api/tenants/{tenant_id}/drafts/{draft_id}/approve`
Explicit user authorization to dispatch message.
```json
// Request
{
  "notes": "Approved by user after review"
}

// Response: 200 OK
{
  "draft_id": "draft_01J...",
  "status": "approved",
  "queued_for_send": true
}
```

---

## 5. Inbound Reply & Webhook Endpoints

### `POST /api/webhooks/inbound/email`
Ingests inbound SMTP reply for MIME processing and threading.
```json
// Request (from MTA or Mailbox parser)
{
  "from": "marcus@cloudwave.tech",
  "to": "outbound@apexcloud.io",
  "subject": "Re: Quick question regarding Kubernetes scaling at CloudWave",
  "in_reply_to": "<unique_msg_id_123@apexcloud.io>",
  "body": "Hi, sounds interesting. Can you send over a 1-pager or deck?",
  "headers": {}
}

// Response: 200 OK
{
  "matched_prospect_id": "prosp_01J...",
  "intent": "information_request",
  "intent_confidence": 0.92,
  "conversation_id": "conv_01J...",
  "recommended_action": "Send 1-pager FinOps summary"
}
```
