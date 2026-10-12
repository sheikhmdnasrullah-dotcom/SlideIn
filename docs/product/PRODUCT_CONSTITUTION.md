# SLIDEIN PRODUCT CONSTITUTION

> **Permanent Core Compass & Operating Standard**  
> Status: Active & Binding  
> Repo: `/Users/nasrullahtanim/Downloads/01-Projects/email-master raw`  
> Owner: Nasrullah Tanim

---

## 1. The Core Purpose and North Star

Slidein is a deployable, AI-assisted prospecting, research, and personalized outreach system for businesses.

> **"Find the right people. Understand their business. Reach out personally. Start more conversations."**

Slidein combines prospect discovery, deep business understanding, explainable lead qualification, personalized outreach generation, controlled sending, and email deliverability infrastructure into **one connected system**.

It is designed for businesses that need a repeatable, auditable process to generate qualified sales conversations without stitching together a dozen disconnected tools or manually researching every prospect.

---

## 2. Inviolable Product Principles

1. **Clarity Over Complexity**  
   The customer experiences an understandable business workflow, not an AI science project. If a capability cannot be explained simply in a 30-second summary, it is over-engineered.
2. **Evidence Over Invented Intelligence**  
   Every prospect qualification score, personalization hook, and business claim must cite traceable evidence (URL, public record, business profile fact). Never fabricate familiarity, past interactions, company metrics, or problems.
3. **Human Control Over Blind Automation**  
   Outbound messaging and irreversible actions require explicit authorization and policy gates. Autonomy levels default to reviewable drafts until explicit policies authorize autonomous dispatch.
4. **Reliability & Deliverability Over Volume**  
   Protect sender reputation and recipient consent. Rate limits, SPF/DKIM/DMARC authentication, bounce/complaint suppression, and provider health override raw sending quotas. Never build functionality to evade anti-spam systems.
5. **One Connected Workflow Over Disconnected Features**  
   Discovery feeds Research. Research feeds Qualification. Qualification feeds Offer Matching. Offer Matching feeds Personalization. Personalization feeds Delivery. Delivery feeds Conversation & Outcome Learning. Each stage passes typed, structured domain data to the next.
6. **Multi-Tenant Isolation First**  
   Every client business is isolated. No prospect, business profile, sending identity, or research artifact may ever leak across tenant boundaries.
7. **Persistence Over Ephemerality**  
   All state (prospects, evidence, drafts, jobs, delivery events) must survive server, worker, and browser restarts.

---

## 3. The 7-Stage Universal Workflow

```mermaid
graph LR
  S1[1. Define ICP & Knowledge] --> S2[2. Discover Prospects]
  S2 --> S3[3. Research & Qualify]
  S3 --> S4[4. Personalized Outreach]
  S4 --> S5[5. Controlled Campaigns]
  S5 --> S6[6. Health & Deliverability]
  S6 --> S7[7. Learn & Improve]
```

- **Stage 1 — Business Knowledge & ICP:** Ingest business identity, products/offers, differentiators, ICP targeting rules, and exclusions.
- **Stage 2 — Prospect Discovery:** Modular source adapters (CSV, directory, search, crawler) find candidate companies and decision-makers.
- **Stage 3 — Research & Qualify:** Crawl public business signals, verify facts, calculate explainable match against ICP criteria.
- **Stage 4 — Personalized Outreach:** Relate documented prospect needs to verified business offers; draft individualized copy without fake claims.
- **Stage 5 — Controlled Campaigns:** Pre-send validation (suppression, validation, policy, rate limits) $\rightarrow$ authorized dispatch.
- **Stage 6 — Monitor Deliverability:** Monitor provider acceptance, bounce/complaint rates, sending identity health, and circuit breakers.
- **Stage 7 — Learn & Improve:** Track real replies, intent classification, positive meetings, and refine targeting criteria.

---

## 4. The Definition of Done for Any Feature

A feature is only complete when:
- It solves an explicit stage in the 7-stage prospect-to-conversation workflow.
- It enforces tenant boundaries on all reads, writes, and background jobs.
- It operates with persistent database storage, schema validation, and typed contracts.
- It reuses existing architectural patterns (`workspace-app` frontend shell, domain services, deliverability engine).
- It handles error states, rate limits, and network retries gracefully.
- It is covered by automated unit/integration tests and verified in real operation.
- It contains no mock data disguised as production functionality.
