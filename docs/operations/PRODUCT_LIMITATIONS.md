# SLIDEIN PRODUCT LIMITATIONS & OPERATIONAL BOUNDARIES

> **System Boundaries, Non-Guarantees, Rate Limits & Honest Capabilities**  
> Status: Authoritative Document  
> Version: 1.0.0

---

## 1. What Slidein Does NOT Do (Non-Goals & Anti-Features)

1. **No Spam Evasion or Filter Circumvention:** Slidein does not rotate disposable shady domains to evade provider penalties, disguise sender identities, or bypass spam filters. Deliverability is achieved through legitimate authentication (SPF/DKIM/DMARC), authentic 1-to-1 personalization, list hygiene, and low volume pacing.
2. **No Guaranteed Inbox Placement:** No software can guarantee inbox placement across major MBPs (Google, Microsoft, Yahoo). Slidein monitors provider signals, bounces, and technical health honestly; it distinguishes between "message accepted by MTA" and "verified inbox placement".
3. **No Unlicensed Scrape Evasion:** Slidein does not bypass CAPTCHAs, use residential proxies to scrape paywalled sites, or violate platform terms of service. It consumes permitted public web data, licensed APIs, and authorized customer inputs.
4. **No Autonomous Unapproved Sending for New Tenants:** Slidein is intentionally designed with safety gates. New client deployments cannot send unreviewed outbound emails until authorized by an operator.

---

## 2. Hard Concurrency & Throughput Limits

| Resource | Boundary | Rationale |
|---|---|---|
| **Max Sending Speed** | 30 emails / hour per mailbox | Protects IP/domain warmup curve and provider reputation |
| **Max Concurrent Research Jobs** | 5 jobs per tenant | Prevents rate limiting from search APIs (Tavily/Serp) |
| **Max Discovered Leads / Batch** | 500 leads per import | Ensures fast in-memory deduplication and review |
| **Daily Volume Cap (Standard)** | 100 emails / day per mailbox | Protects long-term deliverability sustainability |

---

## 3. Cost & Resource Tracking

- **Search API Queries:** Each researched prospect consumes $1-3$ search calls. Usage must be tracked per tenant to prevent unbounded API credit burn.
- **LLM Token Consumption:** Drafting and qualification consume ~800 prompt tokens and ~200 completion tokens per prospect.
- **Storage Retention:** Raw crawled HTML is retained for 14 days; extracted structured `evidence_items` are retained permanently or until prospect deletion.
