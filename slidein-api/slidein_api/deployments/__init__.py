"""Deployments: installed blueprint instances and their lifecycle.

Pure data + transition rules for the founder control plane. No database
changes here — persistence arrives with the control-plane store (M5/M6).
"""

from .lifecycle import (
    ALLOWED_TRANSITIONS,
    DeploymentModel,
    DeploymentRecord,
    DeploymentStatus,
    TransitionError,
    can_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "DeploymentModel",
    "DeploymentRecord",
    "DeploymentStatus",
    "TransitionError",
    "can_transition",
]
