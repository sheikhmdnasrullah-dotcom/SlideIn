# SlideIn — Universal Project & Operational Rules

> **Authority note (2026-10-16):** This root file is a high-level summary created before the engagement capability was documented.
> Where it differs from `docs/` (canonical layout, ADR-0002), **`docs/` prevails**. Figures marked as targets here (placement %, latency, price/cost,
> thresholds) are **proposals, not confirmed requirements**. Prospect Engagement (reply → chat/voice → meeting booking):
> `docs/product/PROSPECT_ENGAGEMENT.md`.


> **Version:** 1.0.0  
> **Authority:** Non-negotiable Operational Standard  
> **Applies to:** All Developers, Agents, and Production Deployments  

---

## 1. Deliverability & Mail Transport Rules

These rules protect the production mail infrastructure (`169.58.206.20`) and preserve sender reputation:

### 1.1 Authentication & Routing
1. **Mandatory SMTP Authentication:** Every message submitted to KumoMTA (`:2587`) must authenticate via SASL (`outbound`). Anonymous relay is strictly forbidden.
2. **Cryptographic DKIM Signing:** Every outbound message must be signed with a 2048-bit DKIM key aligned with the sender domain (`nasrullahtanim.me`, `tanim.social`, `tanim.tech`).
3. **No Header Forgery or Spoofing:** The `From:` header must exactly match the authenticated sender identity. No display-name spoofing.
4. **Legitimate Sender Profiles Only:** All outreach must originate from real, verified profiles:
   - `hello@nasrullahtanim.me`
   - `talk@nasrullahtanim.me`
   - `connect@nasrullahtanim.me`
5. **Pre-Send Verification Mandatory:** No email may be dispatched without prior verification through Reacher (`:8090`). Catch-all and invalid addresses must be isolated.

### 1.2 Primary Inbox Copy Standards
1. **1:1 Peer-to-Peer Tone:** Copy must read like genuine human communication from an industry colleague.
2. **Plain-Text First:** Plain text format is the default. Do not wrap cold emails in multi-column HTML tables, marketing styling, or commercial banners.
3. **Zero Tracking Bloat:** Avoid multiple redirect tracking links or heavy tracking pixels that trigger spam filters.
4. **Commercial Density Control:** Never include pricing figures, "Buy Now" CTAs, or aggressive sales rhetoric.

### 1.3 Autonomous Circuit Breakers
1. **Bounce Threshold:** If the rolling hard-bounce rate exceeds **3.0%** over 100 emails, dispatch is instantly paused.
2. **Complaint Threshold:** If spam complaints exceed **0.05%**, dispatch is instantly paused.
3. **Alerting:** Circuit breaker trips must dispatch immediate notifications to the operator via SSE and webhook.

---

## 2. Multi-Tenant Architecture & Data Isolation Rules

### 2.1 The Anti-Contamination Invariant
1. **Strict Row-Level Partitioning:** Every database table holding client data must have a `tenant_id` column. Every SQL query must include `WHERE tenant_id = :current_tenant`.
2. **Namespace Partitioning in Vector Stores:** Vector lookups must strictly specify the active tenant namespace. Cross-namespace similarity queries are fatal errors.
3. **Differential Learning Privacy:** Platform-level learning (Tier 3 Heuristic Memory) may only ingest anonymized, non-PII structural statistics. Never ingest client leads, prospect names, or proprietary copy into platform models.
4. **Tenant Impersonation Prevention:** Client session tokens are cryptographically signed and scoped to a single `tenant_id`. Any attempt to access another tenant's entity returns `403 Forbidden`.

---

## 3. Frontend & Design System Rules (SlideIn Venture Standard)

Replicated directly from SlideIn Venture (`slidein-venture` / `sv to tanim.social`):

### 3.1 Color & Contrast Invariants
1. **No Raw Hex or Pixel Literals:** Never write `#FF6200`, `18px`, or raw millisecond values in a `.tsx` file. All values must resolve to semantic CSS tokens.
2. **The Contrast Rule 1 (`--accent` vs `--accent-vivid`):**
   - `--accent-vivid` reaches only 2.73:1 against paper. It is **STRICTLY FORBIDDEN** for small text.
   - All orange text must use `--accent` (or `--text-accent` / `--color-flame`) which resolves to `signal` (day) or `brand-hi` (night) to guarantee $\ge 4.5:1$ AA contrast.
   - `--accent-vivid` is reserved strictly for fills and graphical strokes.
3. **The Contrast Rule 2 (`--faint` is NOT text):**
   - `--faint` reaches 1.76:1 on paper. It is reserved for non-text marks (ticks, brackets, dividers). If you are about to set text in it, use `--muted`.
4. **No Pure Black or White:** Never use `#000000` or `#FFFFFF`. The lightest value is `paper-25`; the darkest is `ink-deep`.
5. **No `dark:` Variant Hacks:** Tone and theme are managed at the section and root level. Do not litter components with `dark:bg-...` or `dark:text-...`. Use semantic tokens (`--surface`, `--on-surface`, `--muted`).

### 3.2 Typography & Elements
1. **Role Classes Only:** Use `.font-display`, `.font-body`, and `.font-label`. Never ad-hoc tracking or loose font styles.
2. **Tabular Figures:** All counts, rates, percentages, and timestamps must include `tabular-nums`.
3. **Wordmark Standard:** Use the live-text `<LogoWordmark />` component. Do not introduce standalone icon marks or SVG logos without explicit architectural sign-off.
4. **No Emoji Icons:** Use consistent SVG icons (1.5px stroke).

---

## 4. Engineering & Code Quality Rules

1. **Strict TypeScript:** No `any` types. All API payloads, props, and database records must have strong interfaces.
2. **Async Python API:** All FastAPI routes and database queries must use asynchronous handlers (`async def`, `await`).
3. **Error Boundaries:** Every dashboard view must be wrapped in an ErrorBoundary to prevent full-page crashes.
4. **Verification Gate Before Deploy:** Always run contrast verification and automated test suites before pushing changes to production VPS.

---

## 5. Engagement Rules

1. Agents never invent prices, availability, commitments, or facts; unknown ⇒ escalate.
2. No automated outbound calls or texts; voice is inbound/callback-only, opt-in, pending legal review.
3. AI is disclosed at the start of chat/voice. No booking is stated until the provider confirms.
4. Agent email replies default to human approval and pass the same pre-send gates.
5. No regulatory-compliance claims. Full list: `docs/operations/PRODUCT_LIMITATIONS.md` §4.
