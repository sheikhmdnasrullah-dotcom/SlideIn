"""Slidein universal core — versioned shared configuration.

Shared defaults (prompts, rules, thresholds, workflow definitions) live here
as immutable, monotonically versioned artifacts. The rules:

- Artifacts are content-addressed and frozen once released; in-place edits
  raise ImmutableReleaseError.
- Exactly one version per name is active. Changes take effect only through
  release(), which records approver + evaluation reference.
- Agents (Role.AGENT) can read active shared config but can never release,
  supersede, or roll back.
- Rollback reactivates a prior version; history is append-only, so every
  shared change has a version and an audit trail.

See docs/architecture/SHARED_CONFIGURATION_VERSIONING.md.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from product.core.errors import ImmutableReleaseError
from product.core.scopes import Role


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _content_hash(content: object) -> str:
    canonical = json.dumps(content, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SharedArtifact:
    """One immutable version of a named shared default."""

    name: str
    kind: str  # prompt | rule | threshold | workflow | template
    version: int
    content_hash: str
    released_at: datetime
    released_by: str  # approver identity (never an agent run id)
    evaluation_ref: str  # eval record id; empty only for seed versions
    superseded_by: int | None = None


@dataclass(frozen=True)
class ReleaseRecord:
    """Audit entry for every activation, supersession, and rollback."""

    name: str
    version: int
    action: str  # released | superseded | rolled_back
    actor: str
    at: datetime
    evaluation_ref: str = ""
    reason: str = ""


class SharedDefaultsRegistry:
    """In-memory versioned store for shared product defaults."""

    _WRITER_ROLES = frozenset({Role.PLATFORM_ADMIN, Role.SYSTEM})

    def __init__(self) -> None:
        self._artifacts: dict[str, list[SharedArtifact]] = {}
        self._contents: dict[tuple[str, int], object] = {}
        self._active: dict[str, int] = {}
        self._history: list[ReleaseRecord] = []

    # -- reads (all roles, agents included: shared knowledge is reusable) --

    def get_active(self, name: str) -> tuple[SharedArtifact, object]:
        """Return (artifact, deep-copied content) for the active version."""
        try:
            version = self._active[name]
        except KeyError:
            raise KeyError(f"no shared default named {name!r}") from None
        artifact = self._artifacts[name][version - 1]
        return artifact, copy.deepcopy(self._contents[(name, version)])

    def active_version(self, name: str) -> int:
        return self._active[name]

    def history(self, name: str | None = None) -> tuple[ReleaseRecord, ...]:
        if name is None:
            return tuple(self._history)
        return tuple(r for r in self._history if r.name == name)

    def versions(self, name: str) -> tuple[SharedArtifact, ...]:
        return tuple(self._artifacts.get(name, ()))

    # -- writes (platform admins only, always versioned) --

    def release(
        self,
        name: str,
        kind: str,
        content: object,
        *,
        actor: str,
        role: Role,
        evaluation_ref: str,
        reason: str = "",
    ) -> SharedArtifact:
        """Publish a new immutable version and activate it.

        evaluation_ref is mandatory: a shared change without an evaluation
        record cannot be released. Seed content uses the sentinel "seed".
        """
        self._require_writer(role)
        if not evaluation_ref:
            raise ImmutableReleaseError(
                f"refusing to release {name!r} without an evaluation record"
            )
        prior = self._artifacts.setdefault(name, [])
        version = len(prior) + 1
        artifact = SharedArtifact(
            name=name,
            kind=kind,
            version=version,
            content_hash=_content_hash(content),
            released_at=_utcnow(),
            released_by=actor,
            evaluation_ref=evaluation_ref,
        )
        self._contents[(name, version)] = copy.deepcopy(content)
        if prior:
            old = prior[-1]
            prior[-1] = SharedArtifact(
                name=old.name,
                kind=old.kind,
                version=old.version,
                content_hash=old.content_hash,
                released_at=old.released_at,
                released_by=old.released_by,
                evaluation_ref=old.evaluation_ref,
                superseded_by=version,
            )
            self._history.append(
                ReleaseRecord(
                    name=name,
                    version=old.version,
                    action="superseded",
                    actor=actor,
                    at=_utcnow(),
                    reason=reason,
                )
            )
        prior.append(artifact)
        self._active[name] = version
        self._history.append(
            ReleaseRecord(
                name=name,
                version=version,
                action="released",
                actor=actor,
                at=_utcnow(),
                evaluation_ref=evaluation_ref,
                reason=reason,
            )
        )
        return artifact

    def rollback(
        self, name: str, to_version: int, *, actor: str, role: Role, reason: str
    ) -> SharedArtifact:
        """Reactivate a prior version. History is append-only: the rollback
        itself is recorded and the bad version stays visible."""
        self._require_writer(role)
        prior = self._artifacts.get(name, [])
        if not 1 <= to_version <= len(prior):
            raise KeyError(f"{name!r} has no version {to_version}")
        if not reason:
            raise ImmutableReleaseError("rollback requires a reason")
        self._active[name] = to_version
        self._history.append(
            ReleaseRecord(
                name=name,
                version=to_version,
                action="rolled_back",
                actor=actor,
                at=_utcnow(),
                reason=reason,
            )
        )
        return prior[to_version - 1]

    @classmethod
    def _require_writer(cls, role: Role) -> None:
        if role not in cls._WRITER_ROLES:
            raise ImmutableReleaseError(
                f"role {role.value} may not change shared configuration"
            )


def seed_registry(registry: SharedDefaultsRegistry) -> None:
    """Install the initial universal defaults. Seed content is deliberately
    industry-neutral: no tenant's ICP, tone, or business facts."""
    registry.release(
        "writing.tone.default",
        "prompt",
        {"tone": "professional", "max_sentences": 4, "voice": "neutral"},
        actor="system-seed",
        role=Role.SYSTEM,
        evaluation_ref="seed",
        reason="initial universal defaults",
    )
    registry.release(
        "qualification.score_weights.v1",
        "rule",
        {"weights": {"icp_fit": 0.4, "intent": 0.3, "engagement": 0.3}},
        actor="system-seed",
        role=Role.SYSTEM,
        evaluation_ref="seed",
        reason="initial universal defaults",
    )
    registry.release(
        "workflow.stages.v1",
        "workflow",
        {
            "stages": [
                "discover",
                "research",
                "qualify",
                "match_offer",
                "personalize",
                "validate",
                "execute",
                "measure",
            ]
        },
        actor="system-seed",
        role=Role.SYSTEM,
        evaluation_ref="seed",
        reason="universal industry-neutral pipeline",
    )
