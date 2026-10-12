# SLIDEIN PRODUCT LEARNING PIPELINE

> Status: Authoritative Specification
> Version: 1.0.0
> Implements: directive §3 (classification), §6 (improvement pipeline), §10 (stages)
> Code: `product/core/learning.py`, `product/core/evaluation.py`

---

## 1. Purpose

The pipeline converts operational evidence into shared product improvements
**without** converting tenant-specific knowledge into shared knowledge. It is
deliberate, authorized, evaluated, and versioned at every step — and it is
separate from ordinary tenant workflow execution.

## 2. Candidate record

Every `LearningCandidate` carries: stable ID, origin (tenant or component,
where permitted), category, observation, evidence, fact-vs-hypothesis flag,
affected capability, scope, privacy assessment, confidence, expected benefit,
risks/regressions, evaluation plan, review status, and (after release) a
version reference. Submission requires all of them — a bare hunch with no
evidence or plan cannot enter the pipeline.

### Categories

Shareable in principle (with cross-business evidence):

- `software_defect`, `reliability_improvement`, `performance_improvement`,
  `cost_optimization`, `usability_improvement`, `integration_compatibility`,
  `generic_workflow_improvement`, `cross_business_hypothesis`

Tenant-scoped (can never be validated as shared improvements):

- `tenant_business_insight`, `customer_preference`

If a tenant insight suggests a general truth, it is re-submitted as a new
`cross_business_hypothesis` candidate with its own evidence — the tenant
item itself stays private. Approval of a tenant-scoped category raises
`UnauthorizedPromotion` (asserted by
`test_customer_preference_cannot_be_validated_as_shared`).

Worked examples:

- Tenant prefers pirate tone → update that tenant's `MessagingPreferences`.
  Never touch `writing.tone.default`.
- Dedup drops plus-addressed records → `software_defect` candidate with a
  synthetic repro; fix, evaluate, release as a versioned rule.
- A signal converts well in one industry → scoped `cross_business_hypothesis`;
  it becomes a qualification input only after multi-context evaluation.

## 3. Lifecycle and gates

```
submit ──▶ PENDING ──▶ APPROVED ──▶ RELEASED
               │            │             (rollback via shared registry)
               └──▶ REJECTED (terminal, reason recorded)
```

| Transition | Who | Requires |
|---|---|---|
| submit | any role incl. agents | complete record; changes nothing shared |
| approve | `platform_admin` | pending + `platform_candidate` scope + shareable category + evaluation record |
| reject | `platform_admin` | pending + recorded reason |
| release | `platform_admin` | approved + validated; activates a shared version bound to the candidate's evaluation |

No automatic production change may result from a single customer's outcome:
`submit()` provably leaves shared state untouched
(`test_submission_alone_changes_nothing_shared`), and `release()` refuses
anything that skipped approval (`test_release_requires_approved_state`).

## 4. The twelve pipeline steps (§6) and where they live

1. **Observe** results + permitted telemetry — tenant runs, `platform_operational`.
2. **Detect** anomalies/defects/improvements — Stage 2 automation + human triage.
3. **Classify** by scope — `LearningCategory` + scope at submit time.
4. **Exclude** unauthorized material — provenance gates (`ProvenanceError`).
5. **Create** candidate with evidence — `LearningRegistry.submit()`.
6. **Reproduce** — synthetic test case in an `EvalSuite`.
7. **Evaluate** vs current implementation — `EvalSuite.run()`.
8. **Cross-business check** — all contexts green, no regressions
   (`check_regressions()` must return empty).
9. **Review** security, privacy, cost, behavior — recorded approval note.
10. **Approve/reject** — `approve()` / `reject()`.
11. **Release** versioned — `release()` → new `SharedArtifact` version.
12. **Monitor + roll back** — `SharedDefaultsRegistry.rollback()` with reason.

## 5. Implementation stages (do not skip ahead)

- **Stage 1 (this release):** isolation, structured config, versioned shared
  defaults, memory scopes, candidate registry, suite runner. All present in
  `product/core/` with enforcing tests.
- **Stage 2:** operational telemetry, outcome tracking, tenant usage/cost
  measurement; SQLAlchemy persistence + RLS per `CORE_VS_TENANT_BOUNDARIES.md §5`.
- **Stage 3:** candidate review workflows, defect-vs-insight triage automation.
- **Stage 4:** scheduled multi-context evaluations, release records UI,
  regression alerting on live metrics.
- **Stage 5:** aggregate analysis or model adaptation — only with demonstrated
  need, authorized data-use policy, evaluation coverage, and governance.
  Explicitly not designed here beyond this paragraph.
