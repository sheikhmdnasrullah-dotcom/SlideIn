# THE UNIVERSAL SLIDEIN FLOW (canonical — read before building anything)

> This is a product invariant, not a suggestion. It is hardcoded in
> `product/core/flow.py` and enforced by tests (`product/tests/test_flow.py`)
> and by the adaptation engine. Every coding/agent session MUST read this
> file (and may treat `product/core/flow.py` as the machine source of truth)
> before designing features, workflows, modules, or integrations.

> **Architecture boundary:** `product/core/flow.py` is the current interim guard, not a new permanent backend. The Canonical Architecture keeps `slidein-api` as the customer domain authority. Move this machine definition there during Phase 3, with tested compatibility mappings and one removal condition; do not maintain divergent flow definitions. The existing API's `synthesize` stage is an as-built compatibility concern: its learning responsibility belongs inside `converse` and the activity/overview feedback loop, not an eighth target stage.

## The flow — true for every client, every industry, every time

```
configure ──▶ discover ──▶ research ──▶ qualify ──▶ personalize ──▶ outreach ──▶ converse
   │             │            │            │             │             │            │
 profile      prospects    evidence    qualification  drafts      sent mails   replies
 offers       provenance  provenance  + offer match  (versioned)  + policy    + intent
 icps                                                                            │
                                                        overview ◀── activity ◀──┘
                                                        (loop back to configure)
```

## The rules

1. **The seven stages are fixed and ordered.** Configure → Discover → Research
   → Qualify → Personalize → Outreach → Converse. Do not add, remove, rename,
   reorder, or skip stages.
2. **Everything builds UNDER a stage.** Tools, frameworks, agents, integrations,
   and business logic attach to a stage and vary per client — the flow does not.
   A mortgage shop and a SaaS company run the same seven stages with different
   tools, schemas, prompts, and policies underneath.
3. **Every stage output carries provenance** (see `flow.py` per-stage
   requirements). No output without a source.
4. **Legacy names alias, they don't fork.** `match_offer` → qualify,
   `validate`/`execute` → outreach, `measure`/`booking`/`nurture` → converse.
   New work uses canonical names.
5. **Off-flow proposals are rejected.** The adaptation engine calls
   `assert_flow_aligned()` before persisting any workflow; CI runs
   `test_flow.py`. If you think the product needs a new top-level stage, that
   is an architecture decision for the product owner — not something a coding
   session introduces.
6. **The loop closes:** converse → activity → overview → refine configure.
   Results feed back into configuration; that is how the workspace adapts
   without ever leaving the flow.

## Where things live (examples)

| Under stage | Existing implementations |
|---|---|
| configure | `product/core/tenant.py` (profile/offers/ICPs), workspace config |
| discover | `osint_core` prospecting, `slidein-api` discovery service |
| research | `osint_core` recon modules (evidence + provenance) |
| qualify | qualification agent, ICP scoring, offer match |
| personalize | personalization agent, versioned drafts (`slidein-api`) |
| outreach | sending pipeline + deliverability policy (`PROJECT_POLICY.md` invariants) |
| converse | conversation agent, reply/intent tracking, activity feed |
