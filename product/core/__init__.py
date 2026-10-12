"""Slidein universal core (Stage 1).

Shared product capabilities with enforced boundaries between the universal
core, tenant-owned business context, and the governed product-learning
pipeline. See docs/architecture/CORE_VS_TENANT_BOUNDARIES.md.
"""

from product.core.scopes import (
    ALLOWED_TRANSITIONS,
    PROMOTION_APPROVERS,
    LearningScope,
    Role,
    may_read_scope,
    may_transition,
)
from product.core.errors import (
    BoundaryError,
    CrossTenantAccess,
    ImmutableReleaseError,
    ProvenanceError,
    UnauthorizedPromotion,
)
from product.core.tenant import (
    BusinessIdentity,
    IdealCustomerProfile,
    MessagingPreferences,
    Offer,
    OperatingPolicy,
    TenantConfigStore,
    TenantContext,
)
from product.core.shared import (
    ReleaseRecord,
    SharedArtifact,
    SharedDefaultsRegistry,
    seed_registry,
)
from product.core.memory import MemoryRecord, MemoryStore, PromotionRecord
from product.core.learning import (
    SHAREABLE_CATEGORIES,
    LearningCandidate,
    LearningCategory,
    LearningRegistry,
    ReviewRecord,
    ReviewStatus,
)
from product.core.evaluation import (
    CaseProvenance,
    CaseResult,
    EvalCase,
    EvalContext,
    EvalSuite,
    SuiteReport,
    check_regressions,
)
from product.core.workflow import STAGES, Stage, StageRecord, UniversalWorkflow, WorkflowRun

__all__ = [
    "ALLOWED_TRANSITIONS",
    "PROMOTION_APPROVERS",
    "STAGES",
    "SHAREABLE_CATEGORIES",
    "BoundaryError",
    "BusinessIdentity",
    "CaseProvenance",
    "CaseResult",
    "CrossTenantAccess",
    "EvalCase",
    "EvalContext",
    "EvalSuite",
    "IdealCustomerProfile",
    "ImmutableReleaseError",
    "LearningCandidate",
    "LearningCategory",
    "LearningRegistry",
    "LearningScope",
    "MemoryRecord",
    "MemoryStore",
    "MessagingPreferences",
    "Offer",
    "OperatingPolicy",
    "PromotionRecord",
    "ProvenanceError",
    "ReleaseRecord",
    "ReviewRecord",
    "ReviewStatus",
    "Role",
    "SharedArtifact",
    "SharedDefaultsRegistry",
    "Stage",
    "StageRecord",
    "SuiteReport",
    "TenantConfigStore",
    "TenantContext",
    "UnauthorizedPromotion",
    "UniversalWorkflow",
    "WorkflowRun",
    "check_regressions",
    "may_read_scope",
    "may_transition",
    "seed_registry",
]
