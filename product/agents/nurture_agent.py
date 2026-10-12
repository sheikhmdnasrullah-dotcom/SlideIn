"""
Acquisition OS — Nurture Agent
Determines when and how to engage non-ready prospects.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from product.agents.base import AcquisitionAgent, llm_provider


class NurtureAgent(AcquisitionAgent):
    """
    Nurture Agent: Determines next interaction for non-ready prospects.
    Responds to behavior, not blindly follows a calendar.
    """

    def get_name(self) -> str:
        return "nurture"

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute nurture recommendation.

        Context:
            - org_id: str
            - opportunity_id: str
            - opportunity_state: Dict
            - available_content: List[Dict]
        """
        opportunity_state = context.get("opportunity_state", {})
        behavior = opportunity_state.get("behavior", [])
        intent = opportunity_state.get("intent", {})
        disqualification_risk = opportunity_state.get("disqualification_risk", False)

        # Analyze behavior to determine nurture strategy
        action, reasoning, timing = self._analyze_nurture_strategy(behavior, intent, disqualification_risk)

        # Select appropriate content
        content_id = self._select_content(behavior, intent)

        return {
            "agent": self.get_name(),
            "opportunity_id": context.get("opportunity_id"),
            "recommendation": {
                "action": action,
                "content_id": content_id,
                "timing": (datetime.utcnow() + timedelta(days=timing)).isoformat(),
                "reasoning": reasoning,
                "personalization": self._personalize_nurture_message(behavior, intent),
            },
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _analyze_nurture_strategy(self, behavior: list, intent: Dict, disqualification_risk: bool) -> tuple[str, str, int]:
        if disqualification_risk:
            return "re_engage_or_disqualify", "Prospect may be cooling; decide whether to re-engage", 3

        # Check for renewed interest signals
        renewed_interest = any(
            event.get("type") in ["calculator_use", "content_consumed"]
            for event in behavior[-5:]
        )

        if renewed_interest:
            return "send_value_content", "Prospect showed renewed interest; provide relevant content", 0

        # Check recency
        last_engaged = None
        for event in reversed(behavior):
            if event.get("type") in ["email_open", "link_click", "reply"]:
                last_engaged = event.get("timestamp")
                break

        if last_engaged:
            try:
                engaged_days = (datetime.utcnow() - datetime.fromisoformat(last_engaged.replace("Z", ""))).days
                if engaged_days >= 14:
                    return "re_engage", "No engagement in 2 weeks; re-engage with fresh content", 0
                elif engaged_days >= 7:
                    return "nurture_with_value", "Moderate engagement; continue nurture with value", 3
            except (ValueError, AttributeError):
                pass

        return "nurture", "Continue nurture sequence", 7

    def _select_content(self, behavior: list, intent: Dict) -> Optional[str]:
        # Mock: select content based on behavior
        return "content_refinance_guide"

    def _personalize_nurture_message(self, behavior: list, intent: Dict) -> str:
        recent_topics = set()
        for event in behavior[-5:]:
            content_title = event.get("content_title")
            if content_title:
                recent_topics.add(content_title.lower())

        if "refinance" in recent_topics:
            return "Following up on your recent refinance research..."
        elif "calculator" in recent_topics:
            return "I hope the calculator was helpful..."
        return "I wanted to share something you might find useful..."


class BookingAgent(AcquisitionAgent):
    """
    Booking Agent: Moves qualified prospects toward an appointment.
    """

    def get_name(self) -> str:
        return "booking"

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute booking recommendation.

        Context:
            - org_id: str
            - opportunity_id: str
            - opportunity_state: Dict
            - advisor: Dict
        """
        opportunity_state = context.get("opportunity_state", {})
        advisor = context.get("advisor", {})

        return {
            "agent": self.get_name(),
            "opportunity_id": context.get("opportunity_id"),
            "recommendation": {
                "action": "send_calendar_link",
                "calendar_link": f"https://calendly.com/advisor/{advisor.get('id', 'default')}?utm_source=acquisition-os",
                "proposed_times": [
                    {"start": "2026-10-10T14:00:00Z", "end": "2026-10-10T14:30:00Z"},
                    {"start": "2026-10-10T16:00:00Z", "end": "2026-10-10T16:30:00Z"},
                ],
                "personalization": "Based on what you're looking for, I'd recommend a 30-minute consultation...",
                "reasoning": "Strong purchase intent + active conversation + defined timeframe",
            },
            "generated_at": datetime.utcnow().isoformat(),
        }
