"""Slidein universal core — boundary violation errors.

These exceptions are the executable form of the architectural invariant:
tenant-private material must never silently become shared product behavior.
"""

from __future__ import annotations


class BoundaryError(Exception):
    """Base class for all core/tenant boundary violations."""


class CrossTenantAccess(BoundaryError):
    """A caller tried to read or write another tenant's private scope."""


class UnauthorizedPromotion(BoundaryError):
    """A scope promotion was attempted without an authorized approver or
    along a transition the governance policy does not allow."""


class ImmutableReleaseError(BoundaryError):
    """An attempt to mutate a released (immutable) shared artifact or to
    change shared behavior outside the versioned release process."""


class ProvenanceError(BoundaryError):
    """An evaluation case or shared artifact lacks acceptable provenance
    (synthetic, platform telemetry, or explicitly authorized tenant data)."""
