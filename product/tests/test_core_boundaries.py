"""Slidein universal core — architecture boundary tests (Stage 1).

These tests enforce the permanent invariant: the shared product must never
be silently reshaped by any single tenant's business. Each test maps to an
item in the directive's §9 list. All are DB-free so they run in CI and
locally without infrastructure.
"""

from __future__ import annotations

import pytest

from product.core import (
    BusinessIdentity,
    CaseProvenance,
    EvalCase,
    EvalContext,
    EvalSuite,
    IdealCustomerProfile,
    LearningCategory,
    LearningRegistry,
    LearningScope,
    MemoryStore,
    MessagingPreferences,
    Offer,
    OperatingPolicy,
    Role,
    SharedDefaultsRegistry,
    Stage,
    TenantConfigStore,
    TenantContext,
    UnauthorizedPromotion,
    CrossTenantAccess,
    ImmutableReleaseError,
    ProvenanceError,
    UniversalWorkflow,
    WorkflowRun,
    check_regressions,
    may_transition,
    seed_registry,
)

TENANT_A = "tenant-acme"
TENANT_B = "tenant-globex"


def make_tenant(tenant_id: str, industry: str, tone: str) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        identity=BusinessIdentity(
            name=tenant_id, domain=f"{tenant_id}.example.com", industry=industry
        ),
        offers=(
            Offer(name="Audit", summary="Ops audit", approved_claims=("10 yrs",)),
        ),
        icps=(
            IdealCustomerProfile(name="icp-1", titles=("COO",), industries=(industry,)),
        ),
        exclusions=("competitor.example",),
        terminology={"lead": "opportunity"},
        messaging=MessagingPreferences(tone=tone),
        policy=OperatingPolicy(require_human_approval=True),
    )


@pytest.fixture()
def tenants() -> TenantConfigStore:
    store = TenantConfigStore()
    store.register(make_tenant(TENANT_A, "plumbing", "casual"), role=Role.SYSTEM)
    store.register(make_tenant(TENANT_B, "legal", "formal"), role=Role.SYSTEM)
    return store


@pytest.fixture()
def shared() -> SharedDefaultsRegistry:
    registry = SharedDefaultsRegistry()
    seed_registry(registry)
    return registry


@pytest.fixture()
def memory() -> MemoryStore:
    return MemoryStore()


@pytest.fixture()
def learning(shared: SharedDefaultsRegistry) -> LearningRegistry:
    return LearningRegistry(shared)


def candidate_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "origin": TENANT_A,
        "category": LearningCategory.SOFTWARE_DEFECT,
        "observation": "dedup drops records with plus-addressed emails",
        "evidence": ("job-1 output", "record pair"),
        "is_hypothesis": False,
        "capability": "dedup",
        "scope": LearningScope.PLATFORM_CANDIDATE,
        "privacy_assessment": "no tenant content; synthetic repro attached",
        "confidence": 0.9,
        "expected_benefit": "fewer lost prospects",
        "risks": ("none identified",),
        "evaluation_plan": "dedup suite v3 must stay green",
        "submitted_by_role": Role.AGENT,
    }
    base.update(overrides)
    return base


# -- §9.1: tenant configuration cannot modify shared defaults ----------


def test_tenant_preference_change_leaves_shared_defaults_untouched(
    tenants: TenantConfigStore, shared: SharedDefaultsRegistry
) -> None:
    before, _ = shared.get_active("writing.tone.default")
    tenants.update_messaging(
        TENANT_A,
        MessagingPreferences(tone="pirate"),
        caller_tenant_id=TENANT_A,
        role=Role.TENANT_ADMIN,
    )
    after, content = shared.get_active("writing.tone.default")
    assert after.version == before.version
    assert content == {"tone": "professional", "max_sentences": 4, "voice": "neutral"}
    assert tenants.get(TENANT_A, caller_tenant_id=TENANT_A, role=Role.TENANT_ADMIN).messaging.tone == "pirate"


def test_returned_shared_content_is_a_copy(shared: SharedDefaultsRegistry) -> None:
    _, content = shared.get_active("qualification.score_weights.v1")
    assert isinstance(content, dict)
    content["weights"]["icp_fit"] = 999.0  # mutate the copy
    _, fresh = shared.get_active("qualification.score_weights.v1")
    assert fresh["weights"]["icp_fit"] == 0.4


# -- §9.2: tenant memory cannot be read by another tenant --------------


def test_cross_tenant_memory_read_raises(memory: MemoryStore) -> None:
    record = memory.put(
        scope=LearningScope.TENANT_PRIVATE,
        tenant_id=TENANT_A,
        category="preference",
        content={"tone": "pirate"},
        role=Role.TENANT_ADMIN,
        caller_tenant_id=TENANT_A,
    )
    with pytest.raises(CrossTenantAccess):
        memory.get(record.id, caller_tenant_id=TENANT_B, role=Role.TENANT_ADMIN)
    with pytest.raises(CrossTenantAccess):
        memory.get(record.id, caller_tenant_id=TENANT_B, role=Role.AGENT)


def test_global_search_never_returns_tenant_private(memory: MemoryStore) -> None:
    memory.put(
        scope=LearningScope.TENANT_PRIVATE,
        tenant_id=TENANT_A,
        category="icp",
        content={"note": "acme secret icp signal"},
        role=Role.AGENT,
        caller_tenant_id=TENANT_A,
    )
    memory.put(
        scope=LearningScope.PLATFORM_OPERATIONAL,
        tenant_id=None,
        category="metric",
        content={"note": "queue latency p99"},
        role=Role.SYSTEM,
    )
    # Default search: tenant-private excluded for everyone.
    assert memory.search("secret", caller_tenant_id=TENANT_B, role=Role.AGENT) == ()
    assert memory.search("secret", caller_tenant_id=TENANT_A, role=Role.AGENT) == ()
    # Even with the flag, tenant B's agent cannot see tenant A's memory.
    assert (
        memory.search(
            "secret",
            caller_tenant_id=TENANT_B,
            role=Role.AGENT,
            include_tenant_private=True,
        )
        == ()
    )
    # The owning tenant can search its own memory explicitly.
    own = memory.search(
        "secret",
        caller_tenant_id=TENANT_A,
        role=Role.TENANT_MEMBER,
        include_tenant_private=True,
    )
    assert len(own) == 1
    # Shared telemetry stays searchable.
    assert len(memory.search("latency", caller_tenant_id=TENANT_B, role=Role.AGENT)) == 1


def test_cross_tenant_config_access_raises(tenants: TenantConfigStore) -> None:
    with pytest.raises(CrossTenantAccess):
        tenants.get(TENANT_A, caller_tenant_id=TENANT_B, role=Role.TENANT_ADMIN)
    with pytest.raises(CrossTenantAccess):
        tenants.update_messaging(
            TENANT_A,
            MessagingPreferences(tone="x"),
            caller_tenant_id=TENANT_B,
            role=Role.TENANT_ADMIN,
        )


# -- §9.3: agents cannot promote tenant-private data --------------------


def test_agent_cannot_promote_memory(memory: MemoryStore) -> None:
    record = memory.put(
        scope=LearningScope.TENANT_PRIVATE,
        tenant_id=TENANT_A,
        category="insight",
        content={"note": "this vertical converts on tuesdays"},
        role=Role.AGENT,
        caller_tenant_id=TENANT_A,
    )
    with pytest.raises(UnauthorizedPromotion):
        memory.promote(
            record.id,
            LearningScope.PLATFORM_CANDIDATE,
            approver="agent-run-1",
            approver_role=Role.AGENT,
            reason="looks generally useful",
        )


def test_promotion_skips_are_forbidden_even_for_admins(memory: MemoryStore) -> None:
    record = memory.put(
        scope=LearningScope.TENANT_PRIVATE,
        tenant_id=TENANT_A,
        category="insight",
        content={"note": "x"},
        role=Role.TENANT_ADMIN,
        caller_tenant_id=TENANT_A,
    )
    with pytest.raises(UnauthorizedPromotion):
        memory.promote(
            record.id,
            LearningScope.PLATFORM_RELEASED,
            approver="platform-admin",
            approver_role=Role.PLATFORM_ADMIN,
            reason="shortcut",
        )


def test_authorized_promotion_is_audited(memory: MemoryStore) -> None:
    record = memory.put(
        scope=LearningScope.TENANT_PRIVATE,
        tenant_id=TENANT_A,
        category="defect",
        content={"note": "dedup drops plus-addresses"},
        role=Role.TENANT_ADMIN,
        caller_tenant_id=TENANT_A,
    )
    updated = memory.promote(
        record.id,
        LearningScope.PLATFORM_CANDIDATE,
        approver="platform-admin",
        approver_role=Role.PLATFORM_ADMIN,
        reason="repro attached; no tenant content",
    )
    assert updated.scope is LearningScope.PLATFORM_CANDIDATE
    (entry,) = memory.promotions()
    assert entry.record_id == record.id
    assert entry.approver_role is Role.PLATFORM_ADMIN


def test_no_role_approves_for_agents() -> None:
    for from_scope in LearningScope:
        for to_scope in LearningScope:
            assert may_transition(from_scope, to_scope, Role.AGENT) is False


# -- §9.4/9.7/9.8: versioned, evaluated, rollback-able shared changes ---


def test_shared_release_is_versioned_and_audited(shared: SharedDefaultsRegistry) -> None:
    artifact = shared.release(
        "writing.tone.default",
        "prompt",
        {"tone": "professional", "max_sentences": 5, "voice": "neutral"},
        actor="platform-admin",
        role=Role.PLATFORM_ADMIN,
        evaluation_ref="eval-42",
        reason="raise sentence cap",
    )
    assert artifact.version == 2
    assert shared.active_version("writing.tone.default") == 2
    actions = [r.action for r in shared.history("writing.tone.default")]
    assert actions == ["released", "superseded", "released"]


def test_agent_cannot_release_shared_config(shared: SharedDefaultsRegistry) -> None:
    with pytest.raises(ImmutableReleaseError):
        shared.release(
            "writing.tone.default",
            "prompt",
            {"tone": "pirate"},
            actor="agent-run-1",
            role=Role.AGENT,
            evaluation_ref="eval-1",
        )


def test_release_without_evaluation_record_is_refused(
    shared: SharedDefaultsRegistry,
) -> None:
    with pytest.raises(ImmutableReleaseError):
        shared.release(
            "writing.tone.default",
            "prompt",
            {"tone": "x"},
            actor="platform-admin",
            role=Role.PLATFORM_ADMIN,
            evaluation_ref="",
        )


def test_shared_rollback_reactivates_prior_version(
    shared: SharedDefaultsRegistry,
) -> None:
    shared.release(
        "writing.tone.default",
        "prompt",
        {"tone": "broken"},
        actor="platform-admin",
        role=Role.PLATFORM_ADMIN,
        evaluation_ref="eval-9",
    )
    rolled = shared.rollback(
        "writing.tone.default",
        1,
        actor="platform-admin",
        role=Role.PLATFORM_ADMIN,
        reason="v2 regressed b2b_saas cases",
    )
    assert rolled.version == 1
    assert shared.active_version("writing.tone.default") == 1
    _, content = shared.get_active("writing.tone.default")
    assert content["tone"] == "professional"
    assert shared.history("writing.tone.default")[-1].action == "rolled_back"


# -- §9.5: one tenant outcome cannot auto-publish a global change -------


def test_submission_alone_changes_nothing_shared(
    learning: LearningRegistry, shared: SharedDefaultsRegistry
) -> None:
    learning.submit(**candidate_kwargs())
    assert shared.active_version("writing.tone.default") == 1
    assert shared.active_version("qualification.score_weights.v1") == 1


def test_approval_requires_admin_and_evaluation(learning: LearningRegistry) -> None:
    candidate = learning.submit(**candidate_kwargs())
    with pytest.raises(UnauthorizedPromotion):
        learning.approve(
            candidate.id, actor="agent", role=Role.AGENT, evaluation_ref="eval-1"
        )
    with pytest.raises(UnauthorizedPromotion):
        learning.approve(
            candidate.id, actor="admin", role=Role.PLATFORM_ADMIN, evaluation_ref=""
        )


def test_customer_preference_cannot_be_validated_as_shared(
    learning: LearningRegistry,
) -> None:
    candidate = learning.submit(
        **candidate_kwargs(
            category=LearningCategory.CUSTOMER_PREFERENCE,
            observation="tenant likes pirate tone",
        )
    )
    with pytest.raises(UnauthorizedPromotion):
        learning.approve(
            candidate.id,
            actor="admin",
            role=Role.PLATFORM_ADMIN,
            evaluation_ref="eval-1",
        )


def test_full_pipeline_releases_versioned_change(
    learning: LearningRegistry, shared: SharedDefaultsRegistry
) -> None:
    candidate = learning.submit(**candidate_kwargs())
    learning.approve(
        candidate.id, actor="admin", role=Role.PLATFORM_ADMIN, evaluation_ref="eval-7"
    )
    released = learning.release(
        candidate.id,
        shared_name="dedup.plus_address_fix",
        shared_kind="rule",
        shared_content={"normalize_plus": True},
        actor="admin",
        role=Role.PLATFORM_ADMIN,
    )
    assert released.released_version == 1
    assert shared.active_version("dedup.plus_address_fix") == 1
    (record,) = [r for r in shared.history() if r.action == "released" and r.name == "dedup.plus_address_fix"]
    assert record.evaluation_ref == "eval-7"


def test_release_requires_approved_state(learning: LearningRegistry) -> None:
    candidate = learning.submit(**candidate_kwargs())
    with pytest.raises(UnauthorizedPromotion):
        learning.release(
            candidate.id,
            shared_name="x",
            shared_kind="rule",
            shared_content={},
            actor="admin",
            role=Role.PLATFORM_ADMIN,
        )


# -- §9.6: evaluation dataset provenance --------------------------------


def _case(case_id: str, provenance: CaseProvenance, **kw: object) -> EvalCase:
    params: dict[str, object] = {
        "id": case_id,
        "context": EvalContext.B2B_SAAS,
        "name": case_id,
        "input": {"text": "hi"},
        "check": lambda out: out.get("ok") is True,
        "provenance": provenance,
    }
    params.update(kw)
    return EvalCase(**params)  # type: ignore[arg-type]


def test_unauthorized_cases_cannot_enter_shared_suites() -> None:
    suite = EvalSuite("shared-smoke")
    with pytest.raises(ProvenanceError):
        suite.add_case(_case("c1", CaseProvenance.UNAUTHORIZED))
    with pytest.raises(ProvenanceError):
        suite.add_case(_case("c2", CaseProvenance.AUTHORIZED_TENANT_DATA))
    suite.add_case(_case("c3", CaseProvenance.SYNTHETIC))
    suite.add_case(
        _case(
            "c4",
            CaseProvenance.AUTHORIZED_TENANT_DATA,
            authorization_ref="consent-123",
        )
    )
    assert len(suite.cases) == 2


def test_regression_check_flags_context_specific_breakage() -> None:
    suite = EvalSuite("tone")
    for ctx in EvalContext:
        suite.add_case(
            EvalCase(
                id=f"tone-{ctx.value}",
                context=ctx,
                name=f"tone {ctx.value}",
                input={"context": ctx.value},
                check=lambda out: out.get("tone") == "professional",
                provenance=CaseProvenance.SYNTHETIC,
            )
        )

    def baseline_workflow(_: dict[str, object]) -> dict[str, object]:
        return {"tone": "professional"}

    def candidate_workflow(inp: dict[str, object]) -> dict[str, object]:
        # Helps one context, regresses the rest — must not ship.
        if inp.get("context") == EvalContext.REAL_ESTATE.value:
            return {"tone": "professional", "extra": True}
        return {"tone": "pirate"}

    before = suite.run(baseline_workflow)
    after = suite.run(candidate_workflow)
    assert before.pass_rate() == 1.0
    regressed = check_regressions(before, after)
    assert len(regressed) == 3
    assert f"tone-{EvalContext.REAL_ESTATE.value}" not in regressed


# -- §9.9/9.10: industry-neutral workflow --------------------------------


def _recording_stages() -> dict[Stage, object]:
    def make(name: str):  # noqa: ANN202
        def fn(run: WorkflowRun):  # noqa: ANN202
            ctx = run.tenant_context
            assert isinstance(ctx, TenantContext)
            # Tenant data shapes outputs; stage order never varies.
            return {"note": f"{name}:{ctx.identity.industry}:{ctx.messaging.tone}"}

        return fn

    return {stage: make(stage.value) for stage in Stage}  # type: ignore[misc]


def test_same_pipeline_for_materially_different_tenants(
    tenants: TenantConfigStore, shared: SharedDefaultsRegistry
) -> None:
    engine = UniversalWorkflow(_recording_stages())  # type: ignore[arg-type]
    _, tone = shared.get_active("writing.tone.default")
    runs = []
    for tenant_id, industry in (
        (TENANT_A, "plumbing"),
        (TENANT_B, "legal"),
    ):
        ctx = tenants.get(
            tenant_id, caller_tenant_id=tenant_id, role=Role.TENANT_ADMIN
        )
        assert ctx.identity.industry == industry
        run = engine.run(
            WorkflowRun(
                tenant_id=tenant_id,
                tenant_context=ctx,
                shared_snapshot={"writing.tone.default": tone},
            )
        )
        runs.append(run)
    orders = [[r.stage.value for r in run.stages_executed] for run in runs]
    assert orders[0] == orders[1] == [
        "discover",
        "research",
        "qualify",
        "match_offer",
        "personalize",
        "validate",
        "execute",
        "measure",
    ]
    # Same code path, tenant-specific data in outputs.
    assert "plumbing" in runs[0].state["personalize.note"]
    assert "legal" in runs[1].state["personalize.note"]


def test_new_tenant_type_needs_no_engine_duplication(
    tenants: TenantConfigStore,
) -> None:
    engine = UniversalWorkflow(_recording_stages())  # type: ignore[arg-type]
    tenants.register(
        make_tenant("tenant-orbitals", "satellite-logistics", "terse"),
        role=Role.SYSTEM,
    )
    ctx = tenants.get(
        "tenant-orbitals", caller_tenant_id="tenant-orbitals", role=Role.TENANT_ADMIN
    )
    run = engine.run(
        WorkflowRun(tenant_id="tenant-orbitals", tenant_context=ctx, shared_snapshot={})
    )
    assert [r.stage.value for r in run.stages_executed] == [
        s.value for s in engine.stage_order
    ]
    assert "satellite-logistics" in run.state["research.note"]
