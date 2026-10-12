"""
Acquisition OS — Qualification Agent
Determines whether an opportunity matches the customer's ICP.
"""

from datetime import datetime
from typing import Dict, Any, Optional

from product.agents.base import AcquisitionAgent, llm_provider


class QualificationAgent(AcquisitionAgent):
    """
    Qualification Agent: Determines if an opportunity matches the customer's ICP.
    """

    def get_name(self) -> str:
        return "qualification"

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute qualification on an opportunity.

        Context:
            - org_id: str
            - opportunity_id: str
            - opportunity_profile: Dict
            - icp: Dict
        """
        opportunity_profile = context.get("opportunity_profile", {})
        icp = context.get("icp", {})

        person = opportunity_profile.get("person", {})
        location = person.get("location", "")
        behavior = opportunity_profile.get("behavior", [])

        # Mock qualification logic (replace with real LLM-based evaluation)
        icp_match = self._score_icp_match(person, icp)
        location_match = self._score_location_match(location, icp)
        timeframe_match = self._score_timeframe(behavior)
        property_range_match = self._score_property_range(behavior, icp)

        total = min(100, icp_match + location_match + timeframe_match + property_range_match)

        fit_score = {
            "icp_match": icp_match,
            "location_match": location_match,
            "purchase_timeframe": timeframe_match,
            "property_range": property_range_match,
            "segment": self._determine_segment(person, behavior),
            "total": total,
        }

        reasoning = self._build_reasoning(fit_score, person, location)
        recommended_angle = self._recommend_angle(fit_score, person)

        qualification_stage = "qualified" if total >= 50 else "researching"

        return {
            "agent": self.get_name(),
            "opportunity_id": context.get("opportunity_id"),
            "fit_score": fit_score,
            "opportunity_score": total,
            "qualification_stage": qualification_stage,
            "reasoning": reasoning,
            "recommended_angle": recommended_angle,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _score_icp_match(self, person: Dict, icp: Dict) -> int:
        segments = icp.get("segments", [])
        if not segments:
            return 15  # neutral
        # Mock: if person has certain keywords, score higher
        return 25

    def _score_location_match(self, location: str, icp: Dict) -> int:
        target_locations = icp.get("locations", [])
        if not target_locations:
            return 15
        for target in target_locations:
            if target.lower() in location.lower():
                return 20
        return 5

    def _score_timeframe(self, behavior: list) -> int:
        for event in behavior:
            if event.get("type") == "intent_signal" and "3 months" in event.get("text", "").lower():
                return 15
        return 8

    def _score_property_range(self, behavior: list, icp: Dict) -> int:
        return 10

    def _determine_segment(self, person: Dict, behavior: list) -> Optional[str]:
        # Mock segment determination
        return "first_time_buyer"

    def _build_reasoning(self, fit_score: Dict, person: Dict, location: str) -> str:
        reasons = []
        if fit_score["location_match"] >= 15:
            reasons.append(f"Strong location match ({location})")
        if fit_score["purchase_timeframe"] >= 12:
            reasons.append("purchase timeframe aligns with target")
        if fit_score["property_range"] >= 8:
            reasons.append("within target property range")
        return "; ".join(reasons) if reasons else "Partial match with ICP"

    def _recommend_angle(self, fit_score: Dict, person: Dict) -> str:
        if fit_score["segment"] == "first_time_buyer":
            return "Discuss first-time buyer programs and down payment assistance"
        return "Discuss financing options"
