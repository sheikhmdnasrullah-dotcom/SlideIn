"""Business Brain workspace schema - file layout, versions, task lifecycle.

The Business Brain is the customer-controlled, file-backed layer of Slidein:
human-readable Markdown that owns authoritative business knowledge. The
runtime reads and writes it through this module; the managed API exposes it.

This module is intentionally deterministic. No LLM call is involved in any
validation, rendering or transition decision.
"""

from __future__ import annotations

from typing import Any


BRAIN_SCHEMA_VERSION = 1

BUSINESS_KINDS = (
    "profile",
    "offers",
    "icp",
    "policies",
    "integrations",
)

BUSINESS_FILENAMES = {
    "profile": "profile.md",
    "offers": "offers.md",
    "icp": "icp.md",
    "policies": "policies.md",
    "integrations": "integrations.md",
}

REQUIRED_BUSINESS_FILES = (
    "brain.md",
    "CHANGELOG.md",
    "tasks/index.md",
    "workflows/index.md",
    "knowledge/index.md",
)

TASK_STATUSES = (
    "queued",
    "planning",
    "running",
    "awaiting_approval",
    "verifying",
    "completed",
    "failed",
    "cancelled",
)

TASK_TRANSITIONS = {
    "queued": ("planning", "cancelled"),
    "planning": ("running", "failed", "cancelled"),
    "running": ("awaiting_approval", "verifying", "failed", "cancelled"),
    "awaiting_approval": ("running", "cancelled"),
    "verifying": ("completed", "failed", "cancelled"),
    "completed": (),
    "cancelled": (),
}

TERMINAL_TASK_STATUSES = frozenset({"completed", "cancelled"})

_REACHED_EXECUTION_STATUSES = frozenset(
    {"running", "verifying", "awaiting_approval"}
)

REQUIRED_PROFILE_FIELDS = (
    "legal_name",
    "website_url",
    "industry",
    "company_description",
    "core_value_prop",
)

OPTIONAL_PROFILE_FIELDS = (
    "markets_served",
    "target_roles",
    "brand_voice",
)


REQUIRED_KEYS: dict = {
    "profile": frozenset(REQUIRED_PROFILE_FIELDS),
    "offers": frozenset({"name"}),
    "icp": frozenset({"name"}),
    "policies": frozenset(),
    "integrations": frozenset(),
}


def safe_tenant_segment(tenant_id: str) -> str:
    cleaned = "".join(
        ch if (ch.isalnum() or ch in "._-") else "_"
        for ch in (tenant_id or "")
    ).strip("._")
    return cleaned or "workspace"


def task_filename(task_id: str) -> str:
    return task_id + ".md"


def task_relpath(task_id: str) -> str:
    return "tasks/" + task_id + ".md"


def task_index_relpath() -> str:
    return "tasks/index.md"


def _normalise_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [
        part.strip()
        for part in str(value).replace(";", ",").split(",")
        if part.strip()
    ]


def normalise_fact(kind, fact):
    if kind not in BUSINESS_KINDS:
        raise ValueError("unknown business kind %r" % (kind,))
    allowed = {
        "profile": set(REQUIRED_PROFILE_FIELDS) | set(OPTIONAL_PROFILE_FIELDS),
        "offers": {"name"},
        "icp": {"name"},
        "policies": set(),
        "integrations": set(),
    }[kind]
    out = {}
    for key, value in dict(fact or {}).items():
        if key in ("schema_version", "version", "kind", "updated_at", "updated_by"):
            continue
        if key not in allowed:
            continue
        if isinstance(value, (list, tuple)):
            out[key] = [str(v).strip() for v in value if str(v).strip()]
        elif key in LIST_FACT_FIELDS.get(kind, frozenset()) and isinstance(value, str):
            out[key] = _normalise_list(value)
        else:
            out[key] = str(value).strip() if isinstance(value, str) else value
    for key in allowed:
        out.setdefault(key, [])
    return out


LIST_FACT_FIELDS = {
    "profile": frozenset({"markets_served", "target_roles"}),
    "offers": frozenset({"pain_points_solved", "proof_points"}),
    "icp": frozenset({"industries", "geographies", "target_roles", "required_signals", "exclusion_keywords"}),
}


def task_facts(task_id, *, tenant_id, requested_outcome, workflow_step,
              success_criteria, constraints=None, permitted_tools=None,
              context_refs=None, actor=""):
    return {
        "task_id": task_id,
        "status": "queued",
        "stage": workflow_step,
        "tenant_id": tenant_id,
        "requested_outcome": requested_outcome,
        "requested_by": actor,
        "context_refs": list(context_refs or []),
        "workflow_step": workflow_step,
        "constraints": list(constraints or []),
        "permitted_tools": list(permitted_tools or []),
        "success_criteria": list(success_criteria or []),
        "attempts": 0,
        "checkpoints": [],
        "evidence_refs": [],
        "error": "",
        "created_at": "",
        "updated_at": "",
        "version": 0,
    }


__all__ = [
    "BRAIN_SCHEMA_VERSION",
    "BUSINESS_FILENAMES",
    "BUSINESS_KINDS",
    "REQUIRED_BUSINESS_FILES",
    "REQUIRED_PROFILE_FIELDS",
    "OPTIONAL_PROFILE_FIELDS",
    "TERMINAL_TASK_STATUSES",
    "TASK_STATUSES",
    "TASK_TRANSITIONS",
    "LIST_FACT_FIELDS",
    "normalise_fact",
    "REQUIRED_KEYS",
    "safe_tenant_segment",
    "task_filename",
    "task_index_relpath",
    "task_relpath",
    "task_facts",
]
