"""Booking and calendar integration service.

Rules enforced:
1. Primary default calendar provider is Notion Booking Calendar.
2. If client has an existing dedicated booking link (Cal.com, Calendly, or custom link),
   the system synchronizes with that dedicated link seamlessly.
3. Strict link delivery policy: ZERO links in cold first-touch outreach emails.
   Links are ONLY injected into replies when prospects explicitly express interest
   or ask to speak to a representative.
4. Non-negotiable pricing policy: Monthly fee ($350/mo) is fixed; agents cannot negotiate or discount.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional
from ..errors import SlideinError


class BookingPolicyError(SlideinError):
    """Raised when an outreach policy or calendar invariant is violated."""
    pass


class BookingProvider:
    """Manages scheduling link generation and calendar sync."""

    def __init__(
        self,
        provider_type: str = "notion",
        primary_booking_url: str = "",
        custom_booking_url: Optional[str] = None,
        monthly_price_usd: float = 350.0,
    ) -> None:
        self.provider_type = provider_type.lower()
        self.primary_booking_url = primary_booking_url
        self.custom_booking_url = custom_booking_url
        self.monthly_price_usd = monthly_price_usd

    def get_effective_booking_url(self) -> str:
        """Returns the dedicated custom link if configured, else the Notion booking link."""
        if self.custom_booking_url and self.custom_booking_url.strip():
            return self.custom_booking_url.strip()
        return self.primary_booking_url.strip()

    def generate_scheduling_link(
        self,
        *,
        outreach_stage: str,
        prospect_email: str,
        prospect_name: str = "",
        prospect_intent: str = "",
    ) -> str:
        """Generates a booking link respecting the cold outreach link ban.
        
        Strictly forbids link generation if stage is cold first-touch.
        """
        stage_norm = outreach_stage.strip().lower()
        if stage_norm in ("cold_outreach", "first_touch", "initial_outreach"):
            raise BookingPolicyError(
                "STRICT POLICY VIOLATION: Links are forbidden in first-touch cold emails.",
                code="link_policy_cold_email_violation",
                recovery_action="remove_links_from_cold_template",
            )

        # Allow link only when prospect expresses interest or is in reply phase
        intent_norm = prospect_intent.strip().lower()
        if intent_norm not in ("interested", "information_request", "meeting_requested"):
            # If intent is not clearly interested, do not attach booking links
            raise BookingPolicyError(
                f"Booking links may only be sent when prospect expresses interest (intent={prospect_intent}).",
                code="link_policy_uninterested_prospect",
                recovery_action="escalate_to_human",
            )

        base_url = self.get_effective_booking_url()
        if not base_url:
            raise BookingPolicyError(
                "No booking calendar URL configured for this tenant.",
                code="calendar_not_configured",
                recovery_action="configure_notion_calendar",
            )

        # Pre-fill query parameters where applicable
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}email={prospect_email}&name={prospect_name}".replace(" ", "%20")

    def validate_pricing_offer(self, requested_price_usd: float) -> bool:
        """Enforces non-negotiable monthly pricing."""
        if round(requested_price_usd, 2) < round(self.monthly_price_usd, 2):
            raise BookingPolicyError(
                f"Non-negotiable pricing policy: requested price ${requested_price_usd:.2f} is below fixed monthly rate ${self.monthly_price_usd:.2f}.",
                code="pricing_negotiation_disallowed",
                recovery_action="revert_to_fixed_pricing",
            )
        return True


def scan_content_for_unauthorized_links(text: str) -> list[str]:
    """Scans text for hyperlinks or URLs to ensure cold emails remain link-free."""
    url_pattern = re.compile(
        r"(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[^\s]*)",
        re.IGNORECASE,
    )
    return url_pattern.findall(text)
