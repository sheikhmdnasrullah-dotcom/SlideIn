"""Deployment factory: provision tenants, version configs, map owners.

Additive tables on the shared ``Base`` metadata — ``create_all`` picks
them up with no migration. Nothing here edits existing tables.
"""

from .activation import ActivationService
from .configs import DeploymentConfigService
from .models import (
    CrmFieldMap,
    DeploymentConfig,
    IntegrationConnection,
    ProspectOwnerAssignment,
    TeamOwner,
)
from .owners import OwnerService
from .validation import ValidationService

__all__ = [
    "ActivationService",
    "CrmFieldMap",
    "DeploymentConfig",
    "DeploymentConfigService",
    "IntegrationConnection",
    "OwnerService",
    "ProspectOwnerAssignment",
    "TeamOwner",
    "ValidationService",
]
