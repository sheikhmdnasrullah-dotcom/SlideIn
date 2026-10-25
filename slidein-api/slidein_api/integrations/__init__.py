"""Integration adapters: stable internal interfaces to external systems.

Each adapter hides one vendor behind a small Slidein-owned interface so
workflows never import vendor SDKs directly. v1 ships the interfaces plus
dry-run implementations; real vendors arrive per deployment in M4.
Credential *values* never appear here — adapters receive secret names and
summaries must stay secret-free.
"""

from .adapters import (
    AdapterStatus,
    CalendarAdapter,
    ConnectionInfo,
    CrmAdapter,
    DryRunCalendarAdapter,
    DryRunCrmAdapter,
    DryRunEnrichmentAdapter,
    DryRunMailTransport,
    DryRunMessagingAdapter,
    EnrichmentAdapter,
    MailTransport,
    MessagingAdapter,
)
from .openosint import (
    LOOKUP_SPECS,
    LookupResult,
    OpenOSINTAdapter,
)

__all__ = [
    "AdapterStatus",
    "CalendarAdapter",
    "ConnectionInfo",
    "CrmAdapter",
    "DryRunCalendarAdapter",
    "DryRunCrmAdapter",
    "DryRunEnrichmentAdapter",
    "DryRunMailTransport",
    "DryRunMessagingAdapter",
    "EnrichmentAdapter",
    "LOOKUP_SPECS",
    "LookupResult",
    "MailTransport",
    "MessagingAdapter",
    "OpenOSINTAdapter",
]
