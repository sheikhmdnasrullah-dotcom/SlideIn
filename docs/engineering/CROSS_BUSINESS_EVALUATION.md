# SLIDEIN CROSS-BUSINESS EVALUATION

> Status: Authoritative Specification
> Version: 1.0.0
> Implements: directive §7 (evaluation framework)
> Code: `product/core/evaluation.py`

---

## 1. Principle

A shared change succeeds when it helps — or at least does not regress — a
representative set of materially different business contexts. Improving the
first tenant's results while regressing others is a failed change. The
evaluation suite exists to make that verdict mechanical:
`check_regressions()` returns the IDs of cases that passed before and fail
after; a non-empty result blocks release.

## 2. Contexts (evaluation examples, not product branches)

`EvalContext`: `professional_services`, `b2b_saas`, `real_estate`,
`business_consulting`. More are added as the product expands. The workflow
must contain no per-context conditional logic — contexts are dataset
labels over one industry-neutral pipeline
(`test_same_pipeline_for_materially_different_tenants`).

## 3. Case provenance

Every `EvalCase` declares provenance:

- `synthetic` — preferred; hand-built or generated fixtures.
- `platform_telemetry` — operational patterns with no customer content.
- `authorized_tenant_data` — real tenant material admitted only with an
  `authorization_ref` naming the consent/contract basis.
- `unauthorized` — rejected at admission (`ProvenanceError`); tenant data
  without an authorization ref is likewise rejected.

No handful of examples proves generalization. Suites track which contexts
each capability covers (`SuiteReport.contexts_covered`), and review must
weigh coverage and uncertainty, not just the headline pass rate.

## 4. What to measure

Per capability and context, with a recorded baseline:

- Data accuracy and source attribution; evidence quality.
- Qualification consistency; offer-match relevance.
- Unsupported-claim frequency (must stay at/near zero).
- Personalization quality; duplicate-detection precision/recall.
- Workflow completion; retry/idempotency correctness.
- Suppression enforcement (violations are release-blocking by themselves).
- Tenant isolation (the `test_core_boundaries.py` suite is part of this).
- Resource consumption (tokens, time, provider calls).
- Regression rate vs the previous released version.

## 5. Suites are versioned

`EvalSuite` versions bump on every case admission. Evaluation records cite
`(suite_name, suite_version)` so any release's evidence is reproducible.
Release flow per change:

1. Run the affected suites against current production behavior → baseline.
2. Run against the candidate → candidate report.
3. `check_regressions(baseline, candidate)` must be empty.
4. Attach the report ID as the candidate's `evaluation_ref`; approve; release.
5. Monitor live metrics; roll back on regression (Stage 4 automation).

## 6. Current status (Stage 1)

The runner, provenance gates, and regression check are implemented and
tested (`test_unauthorized_cases_cannot_enter_shared_suites`,
`test_regression_check_flags_context_specific_breakage`). Populating
production suites with synthetic cases per capability/context is Stage 3–4
work; this document defines the contract those suites must satisfy.
