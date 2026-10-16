"""Deployment lifecycle: explicit states and legal transitions.

Only states with real behavior behind them are used. History is
append-only so every pause/update/retire is auditable.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace


class DeploymentStatus(str, enum.Enum):
    PLANNED = "planned"
    AWAITING_CLIENT = "awaiting_client"
    READY = "ready"
    DEPLOYING = "deploying"
    ACTIVE = "active"
    DEGRADED = "degraded"
    PAUSED = "paused"
    UPDATING = "updating"
    RETIRING = "retiring"
    ARCHIVED = "archived"


class DeploymentModel(str, enum.Enum):
    DEDICATED = "dedicated"  # Model B: Slidein-managed host per client
    SHARED = "shared"  # Model A: isolated tenant on shared platform
    CLIENT_OWNED = "client_owned"  # Model C: runs in client infrastructure


ALLOWED_TRANSITIONS: dict[DeploymentStatus, frozenset[DeploymentStatus]] = {
    DeploymentStatus.PLANNED: frozenset({
        DeploymentStatus.AWAITING_CLIENT, DeploymentStatus.READY,
    }),
    DeploymentStatus.AWAITING_CLIENT: frozenset({
        DeploymentStatus.READY, DeploymentStatus.RETIRING,
    }),
    DeploymentStatus.READY: frozenset({
        DeploymentStatus.DEPLOYING, DeploymentStatus.AWAITING_CLIENT,
        DeploymentStatus.RETIRING,
    }),
    DeploymentStatus.DEPLOYING: frozenset({
        DeploymentStatus.ACTIVE, DeploymentStatus.READY,
    }),
    DeploymentStatus.ACTIVE: frozenset({
        DeploymentStatus.DEGRADED, DeploymentStatus.PAUSED,
        DeploymentStatus.UPDATING, DeploymentStatus.RETIRING,
    }),
    DeploymentStatus.DEGRADED: frozenset({
        DeploymentStatus.ACTIVE, DeploymentStatus.PAUSED,
        DeploymentStatus.UPDATING, DeploymentStatus.RETIRING,
    }),
    DeploymentStatus.PAUSED: frozenset({
        DeploymentStatus.ACTIVE, DeploymentStatus.UPDATING,
        DeploymentStatus.RETIRING,
    }),
    DeploymentStatus.UPDATING: frozenset({
        DeploymentStatus.ACTIVE, DeploymentStatus.DEGRADED,
    }),
    DeploymentStatus.RETIRING: frozenset({DeploymentStatus.ARCHIVED}),
    DeploymentStatus.ARCHIVED: frozenset(),
}


class TransitionError(ValueError):
    pass


def can_transition(frm: DeploymentStatus, to: DeploymentStatus) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, frozenset())


@dataclass(frozen=True)
class DeploymentRecord:
    deployment_id: str
    client_name: str
    workspace_id: str  # tenant identity; server-side only
    blueprint_name: str
    blueprint_version: str
    model: DeploymentModel
    environment: str  # e.g. "vps-client1" or "shared-eu-1"
    status: DeploymentStatus = DeploymentStatus.PLANNED
    config_version: str = ""
    connection_refs: tuple[str, ...] = ()  # secret *names*, never values
    history: tuple[tuple[str, str, str, str], ...] = ()  # (frm, to, reason, actor)

    def transition(self, to: DeploymentStatus, *, reason: str, actor: str,
                   ) -> "DeploymentRecord":
        if not reason.strip():
            raise TransitionError("a reason is required for every transition")
        if not can_transition(self.status, to):
            raise TransitionError(f"illegal transition {self.status.value} -> {to.value}")
        entry = (self.status.value, to.value, reason.strip(), actor)
        return replace(self, status=to, history=self.history + (entry,))

    @property
    def is_terminal(self) -> bool:
        return self.status is DeploymentStatus.ARCHIVED

    @property
    def needs_attention(self) -> bool:
        return self.status in (
            DeploymentStatus.DEGRADED, DeploymentStatus.AWAITING_CLIENT,
        )
