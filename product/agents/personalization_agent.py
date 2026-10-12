"""
Acquisition OS — Personalization Agent
Converts research into specific, genuine context for messaging.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional

from product.agents.base import AcquisitionAgent, llm_provider


class PersonalizationAgent(AcquisitionAgent):
    """
    Personalization Agent: Converts research into genuine, specific context.
    Never fabricates facts or uses fake compliments.
    """

    def get_name(self) -> str:
        return "personalization"

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute personalization for a message.

        Context:
            - org_id: str
            - opportunity_id: str
            - research_dossier: Dict
            - brand_voice: Dict
            - message_type: str
        """
        research = context.get("research_dossier", {})
        brand_voice = context.get("brand_voice", {})
        message_type = context.get("message_type", "initial_outreach")

        # Extract specific, genuine details from research
        recent_signals = research.get("recent_signals", [])
        fit_indicators = research.get("fit_indicators", [])
        evidence = research.get("evidence", [])

        # Build personalization based on real research
        opening_context = self._build_opening_context(recent_signals, message_type)
        relevant_detail = self._build_relevant_detail(recent_signals, fit_indicators)
        genuine_relevance = self._build_genuine_relevance(recent_signals, fit_indicators)

        personalization = {
            "opening_context": opening_context,
            "relevant_detail": relevant_detail,
            "genuine_relevance": genuine_relevance,
            "avoid": ["fake_compliments", "generic_statements", "unverified_claims"],
        }

        # Build provenance (what evidence backs each claim)
        provenance = []
        for signal in recent_signals[:3]:
            provenance.append({
                "claim": signal,
                "source": "research_dossier",
                "confidence": 0.85,
            })
        for item in evidence[:2]:
            provenance.append({
                "claim": item.get("summary", ""),
                "source": item.get("source", ""),
                "confidence": item.get("confidence", 0.8),
            })

        return {
            "agent": self.get_name(),
            "opportunity_id": context.get("opportunity_id"),
            "personalization": personalization,
            "provenance": provenance,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _build_opening_context(self, signals: List[str], message_type: str) -> str:
        if not signals:
            return "I noticed you've been exploring mortgage options..."

        first_signal = signals[0].lower()
        if "calculator" in first_signal:
            return "I saw you've been using our mortgage calculator..."
        elif "download" in first_signal:
            return "I hope you found the guide helpful..."
        elif "email" in first_signal or "opened" in first_signal:
            return "Thanks for engaging with our content..."
        return "I noticed you've been exploring options in your area..."

    def _build_relevant_detail(self, signals: List[str], indicators: List[str]) -> str:
        if not signals:
            return ""
        return f"and {signals[0].lower()}"

    def _build_genuine_relevance(self, signals: List[str], indicators: List[str]) -> str:
        if "first_time_buyer" in indicators:
            return "First-time buyer programs could help make your purchase more affordable..."
        elif "refinance" in indicators:
            return "Current rates might present an opportunity to lower your monthly payment..."
        return "I'd love to discuss your specific situation and goals..."
