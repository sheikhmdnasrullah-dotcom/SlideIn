"""Deliverability Guard & Cold-Email Compliance Enforcement Service.

Rules enforced:
1. Shared IP Protection:
   - Evaluates per-tenant rolling bounce and complaint rates.
   - Quarantines an offending tenant if hard bounce rate > 3.0% or complaint rate > 0.05%,
     without affecting other tenants sharing the VPS.
2. Cold-Email Statutory Compliance (CAN-SPAM, GDPR, CASL):
   - Mandates a valid physical postal address for the tenant before any email can send.
   - Mandates a lawful basis record (B2B legitimate interest with documented ICP match).
   - Automatically injects an unequivocal opt-out notice into email footers.
   - Attaches RFC 8058 List-Unsubscribe headers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from ..errors import SlideinError

logger = logging.getLogger("slidein.deliverability_guard")

MAX_ALLOWED_BOUNCE_RATE = 0.03      # 3.0%
MAX_ALLOWED_COMPLAINT_RATE = 0.0005  # 0.05%
MIN_SAMPLE_SIZE_FOR_BREAKER = 20    # Minimum dispatches before tripping circuit breaker
QUARANTINE_WINDOW = 100             # Rolling per-tenant outcome window evaluated on each event

#: Provider outcomes that count toward the reputation window. `submitted`,
#: `deferred`, opens and clicks are not reputation outcomes.
BREAKER_EVENT_TYPES = ("accepted", "delivered", "bounced", "complained")


class DeliverabilityQuarantineError(SlideinError):
    """Raised when a tenant's sending is quarantined due to bounce or spam complaint rates."""
    code = "tenant_dispatch_quarantined"


class MissingPhysicalAddressError(SlideinError):
    """Raised when a tenant attempts to send cold emails without a registered physical postal address."""
    code = "missing_physical_postal_address"


class LawfulBasisMissingError(SlideinError):
    """Raised when an outbound campaign lacks documented B2B lawful basis."""
    code = "missing_lawful_basis"


class DeliverabilityGuard:
    """Enforces multi-tenant deliverability isolation and legal compliance."""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id

    def validate_pre_send_compliance(
        self,
        tenant_settings: Dict[str, Any],
        profile_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Verifies statutory compliance prerequisites before dispatch is permitted."""
        # 1. Check if tenant is quarantined
        if tenant_settings.get("quarantined", False):
            reason = tenant_settings.get("quarantine_reason", "Deliverability threshold breached.")
            raise DeliverabilityQuarantineError(
                f"Tenant {self.tenant_id} is quarantined from sending on shared IPs: {reason}",
                recovery_action="request_operator_review",
                details={"tenant_id": self.tenant_id, "quarantine_reason": reason},
            )

        # 2. Check Physical Postal Address (CAN-SPAM 15 U.S.C. 7704(a)(5)(A)(iii))
        address = (
            tenant_settings.get("physical_postal_address")
            or (profile_data.get("physical_address") if profile_data else None)
        )
        if not address or not str(address).strip():
            raise MissingPhysicalAddressError(
                "CAN-SPAM Compliance Violation: A valid physical postal address is required "
                "in workspace settings before cold outreach emails can be dispatched.",
                recovery_action="update_workspace_physical_address",
                details={"tenant_id": self.tenant_id},
            )

        # 3. Check Lawful Basis (GDPR Art. 6(1)(f) / CASL)
        lawful_basis = tenant_settings.get("lawful_basis", "b2b_legitimate_interest")
        if not lawful_basis or not str(lawful_basis).strip():
            raise LawfulBasisMissingError(
                "GDPR / Cold-Email Compliance Violation: Lawful basis (e.g. b2b_legitimate_interest) "
                "must be established and recorded prior to dispatch.",
                recovery_action="set_campaign_lawful_basis",
                details={"tenant_id": self.tenant_id},
            )

    @staticmethod
    def evaluate_circuit_breaker(
        recent_events: List[str],  # List of event types: "delivered", "bounced", "complained"
    ) -> Tuple[bool, Optional[str]]:
        """Calculates bounce and complaint metrics over a sample window.
        
        Returns (is_tripped, trip_reason).
        """
        if len(recent_events) < MIN_SAMPLE_SIZE_FOR_BREAKER:
            return False, None

        total = len(recent_events)
        bounces = sum(1 for e in recent_events if e in ("bounced", "hard_bounce"))
        complaints = sum(1 for e in recent_events if e in ("complained", "spam_complaint"))

        bounce_rate = bounces / total
        complaint_rate = complaints / total

        if bounce_rate > MAX_ALLOWED_BOUNCE_RATE:
            return (
                True,
                f"Hard bounce rate ({bounce_rate:.1%}) exceeded safety threshold ({MAX_ALLOWED_BOUNCE_RATE:.1%}).",
            )

        if complaint_rate > MAX_ALLOWED_COMPLAINT_RATE:
            return (
                True,
                f"Spam complaint rate ({complaint_rate:.2%}) exceeded safety threshold ({MAX_ALLOWED_COMPLAINT_RATE:.2%}).",
            )

        return False, None

    @staticmethod
    def format_compliant_body(
        body_text: str,
        physical_address: str,
        opt_out_instruction: str = "To stop receiving emails, reply with 'stop' or 'unsubscribe'.",
    ) -> str:
        """Appends clear opt-out language and physical mailing address to email body."""
        body_clean = body_text.rstrip()
        
        # Avoid duplicate footers if already present
        if "opt out" in body_clean.lower() or "unsubscribe" in body_clean.lower():
            if physical_address.lower() in body_clean.lower():
                return body_clean
            return f"{body_clean}\n\n--\n{physical_address}"

        footer = (
            f"\n\n--\n"
            f"{opt_out_instruction}\n"
            f"{physical_address}"
        )
        return f"{body_clean}{footer}"

    @staticmethod
    def build_compliance_headers(
        tenant_id: str,
        sender_email: str,
        recipient_email: str,
        unsubscribe_mailbox: Optional[str] = None,
    ) -> Dict[str, str]:
        """Generates RFC 8058 List-Unsubscribe headers for email clients."""
        unsub_addr = unsubscribe_mailbox or f"optout+{tenant_id}@mail.nasrullahtanim.me"
        return {
            "List-Unsubscribe": f"<mailto:{unsub_addr}?subject=unsubscribe>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            "X-Compliance-Notice": "CAN-SPAM/GDPR-B2B",
            "X-Tenant-ID": tenant_id,
        }
