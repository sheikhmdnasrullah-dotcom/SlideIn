"""Shared backend services.

Every section of the client workspace is a thin view over these services.
No service duplicates another's logic: the stage runner calls them, the
API routes call them, and the Overview reads aggregates they produce.
"""

from .activity import ActivityService
from .config import ConfigService
from .conversations import ConversationService
from .discovery import DiscoveryService
from .overview import OverviewService
from .personalization import PersonalizationService
from .qualification import QualificationService
from .osint import OSINTService
from .outreach import OutreachService
from .research import ResearchService
from .suppression import SuppressionService
from .transport import DryRunTransport, SMTPTransport, TransportRegistry, get_transport

__all__ = [
    "ActivityService",
    "ConfigService",
    "ConversationService",
    "DiscoveryService",
    "DryRunTransport",
    "OverviewService",
    "PersonalizationService",
    "QualificationService",
    "OSINTService",
    "OutreachService",
    "ResearchService",
    "SMTPTransport",
    "SuppressionService",
    "TransportRegistry",
    "get_transport",
]
