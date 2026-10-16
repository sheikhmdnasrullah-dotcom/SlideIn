"""Workflow blueprints: versioned, reusable process definitions.

A blueprint describes *how* a workflow runs (stages, config needs,
approval gates). A deployment (`slidein_api.deployments`) is one
client's installed instance of a blueprint. No per-client forks.
"""

from .registry import (
    ApprovalGate,
    BLUEPRINTS,
    ConfigField,
    ValidationResult,
    WorkflowBlueprint,
    get_blueprint,
    list_blueprints,
    validate_deployment_config,
)

__all__ = [
    "ApprovalGate",
    "BLUEPRINTS",
    "ConfigField",
    "ValidationResult",
    "WorkflowBlueprint",
    "get_blueprint",
    "list_blueprints",
    "validate_deployment_config",
]
