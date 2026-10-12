"""Slidein universal core — learning candidate registry.

A LearningCandidate is the unit of product learning: one observation, with
evidence, a fact/hypothesis distinction, an evaluation plan, and a review
lifecycle. The registry enforces the governance pipeline:

- Anyone (including agents) may *submit* a candidate. Submission never
  changes shared behavior.
- Only Role.PLATFORM_ADMIN may approve (candidate -> validated, requires an
  evaluation record) or release (validated -> released, activates a new
  shared version through SharedDefaultsRegistry).
- Scope changes happen only inside this registry with a recorded approver.
  There is no API by which an agent promotes a candidate by itself.
- Rejection is terminal and recorded; releases can be rolled back through
  the shared registry, which appends to the same audit trail.

See docs/architecture/PRODUCT_LEARNING_PIPELINE.md.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from product.core.errors import UnauthorizedPromotion
from product.core.scopes import LearningScope, Role
from product.core.shared import SharedDefaultsRegistry


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LearningCategory(str, Enum):
    """What kind of learning this candidate represents. Business-specific
    categories must never resolve into shared changes without
    cross-business evidence (see evaluation.py)."""

    SOFTWARE_DEFECT = "software_defect"
    RELIABILITY_IMPROVEMENT = "reliability_improvement"
    PERFORMANCE_IMPROVEMENT = "performance_improvement"
    COST_OPTIMIZATION = "cost_optimization"
    USABILITY_IMPROVEMENT = "usability_improvement"
    INTEGRATION_COMPATIBILITY = "integration_compatibility"
    GENERIC_WORKFLOW_IMPROVEMENT = "generic_workflow_improvement"
    CROSS_BUSINESS_HYPOTHESIS = "cross_business_hypothesis"
    TENANT_BUSINESS_INSIGHT = "tenant_business_insight"
    CUSTOMER_PREFERENCE = "customer_preference"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RELEASED = "released"


# Categories that are *eligible in principle* for shared promotion. Tenant
# business insights and customer preferences stay tenant-private; if they
# inspire a general hypothesis, that hypothesis is submitted as a separate
# CROSS_BUSINESS_HYPOTHESIS candidate with its own evidence.
SHAREABLE_CATEGORIES = frozenset(
    {
        LearningCategory.SOFTWARE_DEFECT,
        LearningCategory.RELIABILITY_IMPROVEMENT,
        LearningCategory.PERFORMANCE_IMPROVEMENT,
        LearningCategory.COST_OPTIMIZATION,
        LearningCategory.USABILITY_IMPROVEMENT,
        LearningCategory.INTEGRATION_COMPATIBILITY,
        LearningCategory.GENERIC_WORKFLOW_IMPROVEMENT,
        LearningCategory.CROSS_BUSINESS_HYPOTHESIS,
    }
)


@dataclass(frozen=True)
class LearningCandidate:
    """Immutable snapshot. State advances only via LearningRegistry methods,
    which return new snapshots and record the transition."""

    id: str
    origin: str  # tenant id or system component name (where permitted)
    category: LearningCategory
    observation: str
    evidence: tuple[str, ...]
    is_hypothesis: bool  # True = hypothesis, False = established fact
    capability: str  # affected product capability, e.g. "dedup", "scoring"
    scope: LearningScope
    privacy_assessment: str
    confidence: float  # 0.0 - 1.0, self-reported by submitter
    expected_benefit: str
    risks: tuple[str, ...]
    evaluation_plan: str
    review_status: ReviewStatus = ReviewStatus.PENDING
    evaluation_ref: str = ""
    released_version: int | None = None
    submitted_by_role: Role = Role.AGENT
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True)
class ReviewRecord:
    candidate_id: str
    action: str  # submitted | approved | rejected | released
    actor: str
    actor_role: Role
    at: datetime = field(default_factory=_utcnow)
    note: str = ""


class LearningRegistry:
    """Governance state machine for learning candidates."""

    def __init__(self, shared: SharedDefaultsRegistry) -> None:
        self._shared = shared
        self._candidates: dict[str, LearningCandidate] = {}
        self._reviews: list[ReviewRecord] = []

    def submit(
        self,
        *,
        origin: str,
        category: LearningCategory,
        observation: str,
        evidence: tuple[str, ...] | list[str],
        is_hypothesis: bool,
        capability: str,
        scope: LearningScope,
        privacy_assessment: str,
        confidence: float,
        expected_benefit: str,
        risks: tuple[str, ...] | list[str],
        evaluation_plan: str,
        submitted_by_role: Role,
    ) -> LearningCandidate:
        """Record a candidate. Submission is always allowed and never
        changes shared behavior; new candidates start in review."""
        if scope not in (
            LearningScope.TENANT_PRIVATE,
            LearningScope.PLATFORM_OPERATIONAL,
            LearningScope.PLATFORM_CANDIDATE,
        ):
            raise UnauthorizedPromotion(
                f"candidates must be submitted as tenant_private, "
                f"platform_operational, or platform_candidate (got {scope.value})"
            )
        candidate = LearningCandidate(
            id=str(uuid.uuid4()),
            origin=origin,
            category=category,
            observation=observation,
            evidence=tuple(evidence),
            is_hypothesis=is_hypothesis,
            capability=capability,
            scope=scope,
            privacy_assessment=privacy_assessment,
            confidence=max(0.0, min(1.0, confidence)),
            expected_benefit=expected_benefit,
            risks=tuple(risks),
            evaluation_plan=evaluation_plan,
            submitted_by_role=submitted_by_role,
        )
        self._candidates[candidate.id] = candidate
        self._reviews.append(
            ReviewRecord(
                candidate_id=candidate.id,
                action="submitted",
                actor=origin,
                actor_role=submitted_by_role,
            )
        )
        return copy.deepcopy(candidate)

    def approve(
        self,
        candidate_id: str,
        *,
        actor: str,
        role: Role,
        evaluation_ref: str,
        note: str = "",
    ) -> LearningCandidate:
        """platform_candidate -> platform_validated. Requires a platform
        admin, an evaluation record, and a shareable category."""
        candidate = self._require(candidate_id)
        if role is not Role.PLATFORM_ADMIN:
            raise UnauthorizedPromotion(
                f"role {role.value} may not approve learning candidates"
            )
        if candidate.review_status is not ReviewStatus.PENDING:
            raise UnauthorizedPromotion(
                f"candidate {candidate_id} is {candidate.review_status.value}, not pending"
            )
        if candidate.scope is not LearningScope.PLATFORM_CANDIDATE:
            raise UnauthorizedPromotion(
                "only platform_candidate items can be approved; "
                "tenant_private items must be promoted to candidate first"
            )
        if candidate.category not in SHAREABLE_CATEGORIES:
            raise UnauthorizedPromotion(
                f"category {candidate.category.value} is tenant-scoped and "
                f"cannot be validated as a shared improvement"
            )
        if not evaluation_ref:
            raise UnauthorizedPromotion("approval requires an evaluation record")
        updated = self._replace(
            candidate,
            scope=LearningScope.PLATFORM_VALIDATED,
            review_status=ReviewStatus.APPROVED,
            evaluation_ref=evaluation_ref,
        )
        self._reviews.append(
            ReviewRecord(
                candidate_id=candidate_id,
                action="approved",
                actor=actor,
                actor_role=role,
                note=note,
            )
        )
        return updated

    def reject(
        self, candidate_id: str, *, actor: str, role: Role, note: str
    ) -> LearningCandidate:
        candidate = self._require(candidate_id)
        if role is not Role.PLATFORM_ADMIN:
            raise UnauthorizedPromotion(
                f"role {role.value} may not reject learning candidates"
            )
        if candidate.review_status is not ReviewStatus.PENDING:
            raise UnauthorizedPromotion("only pending candidates can be rejected")
        if not note:
            raise UnauthorizedPromotion("rejection requires a recorded reason")
        updated = self._replace(candidate, review_status=ReviewStatus.REJECTED)
        self._reviews.append(
            ReviewRecord(
                candidate_id=candidate_id,
                action="rejected",
                actor=actor,
                actor_role=role,
                note=note,
            )
        )
        return updated

    def release(
        self,
        candidate_id: str,
        *,
        shared_name: str,
        shared_kind: str,
        shared_content: object,
        actor: str,
        role: Role,
        reason: str = "",
    ) -> LearningCandidate:
        """platform_validated -> platform_released. Activates a new shared
        version through the shared registry, so the change is versioned,
        attributed to the candidate's evaluation, and rollback-able."""
        candidate = self._require(candidate_id)
        if role is not Role.PLATFORM_ADMIN:
            raise UnauthorizedPromotion(
                f"role {role.value} may not release shared changes"
            )
        if (
            candidate.review_status is not ReviewStatus.APPROVED
            or candidate.scope is not LearningScope.PLATFORM_VALIDATED
        ):
            raise UnauthorizedPromotion(
                "only approved + validated candidates can be released"
            )
        artifact = self._shared.release(
            shared_name,
            shared_kind,
            shared_content,
            actor=actor,
            role=role,
            evaluation_ref=candidate.evaluation_ref or candidate.id,
            reason=reason or f"learning {candidate.id}",
        )
        updated = self._replace(
            candidate,
            scope=LearningScope.PLATFORM_RELEASED,
            review_status=ReviewStatus.RELEASED,
            released_version=artifact.version,
        )
        self._reviews.append(
            ReviewRecord(
                candidate_id=candidate_id,
                action="released",
                actor=actor,
                actor_role=role,
                note=f"{shared_name} v{artifact.version}",
            )
        )
        return updated

    def get(self, candidate_id: str) -> LearningCandidate:
        return copy.deepcopy(self._require(candidate_id))

    def reviews(self) -> tuple[ReviewRecord, ...]:
        return tuple(self._reviews)

    def _require(self, candidate_id: str) -> LearningCandidate:
        try:
            return self._candidates[candidate_id]
        except KeyError:
            raise UnauthorizedPromotion(
                f"unknown learning candidate {candidate_id!r}"
            ) from None

    def _replace(self, candidate: LearningCandidate, **changes: object) -> LearningCandidate:
        updated = LearningCandidate(
            **{**candidate.__dict__, **changes}  # type: ignore[arg-type]
        )
        self._candidates[candidate.id] = updated
        return copy.deepcopy(updated)
