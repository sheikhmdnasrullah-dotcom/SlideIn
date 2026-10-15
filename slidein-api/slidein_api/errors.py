"""Errors and failure taxonomy.

Every stage failure maps to one of these codes so the UI can show the
reason and the recovery action without parsing free text.
"""

from __future__ import annotations

from enum import Enum


class FailureCode(str, Enum):
    # Configuration problems — fixable by the user in Business Profile.
    PROFILE_MISSING = "profile_missing"
    PROFILE_INCOMPLETE = "profile_incomplete"
    OFFER_MISSING = "offer_missing"
    ICP_MISSING = "icp_missing"
    CONFIG_VERSION_CONFLICT = "config_version_conflict"

    # Input problems — fixable on the record.
    PROSPECT_NOT_FOUND = "prospect_not_found"
    PROSPECT_DUPLICATE = "prospect_duplicate"
    PROSPECT_INVALID = "prospect_invalid"
    DRAFT_NOT_FOUND = "draft_not_found"
    DRAFT_NOT_APPROVED = "draft_not_approved"

    # Precondition problems — a prerequisite stage has not run.
    STAGE_PREREQUISITE = "stage_prerequisite"
    INVALID_TRANSITION = "invalid_transition"

    # External / provider problems — usually retryable.
    SOURCE_UNAVAILABLE = "source_unavailable"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "rate_limited"
    TRANSPORT_REJECTED = "transport_rejected"

    # Policy blocks.
    SUPPRESSED = "suppressed"
    NOT_AUTHORIZED = "not_authorized"
    TENANT_FORBIDDEN = "tenant_forbidden"
    APPROVAL_REQUIRED = "approval_required"

    UNKNOWN = "unknown"


#: Whether a failed run may be retried by the same caller without
#: changing anything. Config/input problems are not retryable — retrying
#: them just burns a run; the user has to change something first.
RETRYABLE: frozenset[str] = frozenset(
    {
        FailureCode.SOURCE_UNAVAILABLE.value,
        FailureCode.PROVIDER_UNAVAILABLE.value,
        FailureCode.RATE_LIMITED.value,
        FailureCode.TRANSPORT_REJECTED.value,
    }
)

#: The recovery action the UI should offer for each failure code.
RECOVERY_ACTION: dict[str, str] = {
    FailureCode.PROFILE_MISSING.value: "create_business_profile",
    FailureCode.PROFILE_INCOMPLETE.value: "complete_business_profile",
    FailureCode.OFFER_MISSING.value: "add_offer",
    FailureCode.ICP_MISSING.value: "define_icp",
    FailureCode.CONFIG_VERSION_CONFLICT.value: "review_config_version",
    FailureCode.PROSPECT_NOT_FOUND.value: "return_to_discovery",
    FailureCode.PROSPECT_DUPLICATE.value: "merge_duplicate",
    FailureCode.PROSPECT_INVALID.value: "fix_prospect_record",
    FailureCode.DRAFT_NOT_FOUND.value: "regenerate_draft",
    FailureCode.DRAFT_NOT_APPROVED.value: "review_draft",
    FailureCode.STAGE_PREREQUISITE.value: "run_prerequisite_stage",
    FailureCode.INVALID_TRANSITION.value: "review_prospect_status",
    FailureCode.SOURCE_UNAVAILABLE.value: "retry_stage",
    FailureCode.PROVIDER_UNAVAILABLE.value: "retry_stage",
    FailureCode.RATE_LIMITED.value: "retry_stage_later",
    FailureCode.TRANSPORT_REJECTED.value: "retry_stage",
    FailureCode.SUPPRESSED.value: "review_suppression",
    FailureCode.NOT_AUTHORIZED.value: "request_authorization",
    FailureCode.TENANT_FORBIDDEN.value: "switch_workspace",
    FailureCode.APPROVAL_REQUIRED.value: "approve_draft",
    FailureCode.UNKNOWN.value: "retry_stage",
}


class SlideinError(Exception):
    """Base error carrying a machine-readable failure code."""

    code = FailureCode.UNKNOWN.value

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict | None = None,
        recovery_action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details or {}
        self.recovery_action = recovery_action or RECOVERY_ACTION.get(self.code, "retry_stage")

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "recovery_action": self.recovery_action,
            "retryable": self.retryable,
        }


class ValidationError(SlideinError):
    code = FailureCode.PROSPECT_INVALID.value


class ConfigError(SlideinError):
    code = FailureCode.PROFILE_INCOMPLETE.value


class PrerequisiteError(SlideinError):
    code = FailureCode.STAGE_PREREQUISITE.value


class TransitionError(SlideinError):
    code = FailureCode.INVALID_TRANSITION.value


class PermissionError_(SlideinError):
    code = FailureCode.NOT_AUTHORIZED.value


class TenantForbiddenError(SlideinError):
    code = FailureCode.TENANT_FORBIDDEN.value


class SuppressedError(SlideinError):
    code = FailureCode.SUPPRESSED.value


class ProviderError(SlideinError):
    code = FailureCode.PROVIDER_UNAVAILABLE.value


class NotFoundError(SlideinError):
    code = FailureCode.PROSPECT_NOT_FOUND.value


# Avoid shadowing the builtin for callers that `from .errors import *`.
PermissionDenied = PermissionError_
NotFound = NotFoundError
