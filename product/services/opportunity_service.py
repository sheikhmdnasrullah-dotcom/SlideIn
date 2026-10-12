"""
Acquisition OS — Opportunity Service
Business logic for opportunity operations.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from product.services.acquisition_engine import AcquisitionEngine
from product.api.schemas import OpportunityState, FitScoreSchema, IntentSchema


class OpportunityService:
    """Service layer for opportunity operations."""

    def __init__(self, db_repository, event_publisher, ai_orchestrator):
        self.db = db_repository
        self.events = event_publisher
        self.ai = ai_orchestrator

    async def create_opportunity(self, org_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new opportunity."""
        person = payload.get("person", {})
        now = datetime.utcnow().isoformat()

        opportunity = {
            "id": f"opp_{self._generate_id()}",
            "org_id": org_id,
            "person": person,
            "opportunity_score": 0,
            "fit": {},
            "intent": {},
            "state": OpportunityState.DISCOVERED.value,
            "qualification": {},
            "next_best_action": "research_opportunity",
            "next_best_action_reason": "New opportunity discovered",
            "next_action_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            "tags": [],
            "behavior": [],
            "conversation": [],
            "appointment": None,
            "provenance": {
                "source": payload.get("source", "inbound"),
                "discovery_signals": payload.get("discovery_signals", []),
                "research_evidence": [],
                "confidence": "medium",
            },
            "lifecycle": {
                "discovered_at": now,
                "last_contacted_at": None,
                "last_engaged_at": None,
                "next_action_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                "state": OpportunityState.DISCOVERED.value,
                "state_history": [
                    {
                        "state": OpportunityState.DISCOVERED.value,
                        "entered_at": now,
                        "exited_at": None,
                        "reason": "Opportunity discovered",
                    }
                ],
            },
            "custom_fields": payload.get("custom_fields", {}),
            "created_at": now,
            "updated_at": now,
            "version": 1,
        }

        await self.db.opportunities.create(opportunity)
        await self.events.publish("opportunity_discovered", opportunity)

        return opportunity

    async def research_opportunity(self, org_id: str, opportunity_id: str, depth: str = "standard") -> Dict[str, Any]:
        """Run the Research Agent on an opportunity."""
        opportunity = await self.db.opportunities.get(org_id, opportunity_id)
        if not opportunity:
            raise ValueError("Opportunity not found")

        # Delegate to AI orchestrator
        result = await self.ai.research_opportunity(org_id, opportunity_id, depth)

        # Update opportunity
        opportunity["research_dossier"] = result.get("dossier")
        opportunity = AcquisitionEngine.transition(
            opportunity,
            OpportunityState.RESEARCHED,
            reason="Research completed",
        )
        opportunity["opportunity_score"] = max(opportunity.get("opportunity_score", 0), result.get("opportunity_score", 45))
        opportunity["next_best_action"], opportunity["next_best_action_reason"] = AcquisitionEngine.get_next_best_action(opportunity)

        await self.db.opportunities.update(org_id, opportunity_id, opportunity)
        await self.events.publish("opportunity_researched", opportunity)

        return opportunity

    async def qualify_opportunity(self, org_id: str, opportunity_id: str) -> Dict[str, Any]:
        """Run the Qualification Agent on an opportunity."""
        opportunity = await self.db.opportunities.get(org_id, opportunity_id)
        if not opportunity:
            raise ValueError("Opportunity not found")

        result = await self.ai.qualify_opportunity(org_id, opportunity_id)

        opportunity["fit"] = result.get("fit_score", {}).dict()
        opportunity["opportunity_score"] = max(opportunity.get("opportunity_score", 0), result.get("opportunity_score", 70))
        opportunity["qualification"] = {
            "stage": result.get("qualification_stage", "qualified"),
            "recommended_angle": result.get("recommended_angle", ""),
            "answers": {},
        }
        opportunity = AcquisitionEngine.transition(
            opportunity,
            OpportunityState.QUALIFIED,
            reason=result.get("reasoning", "Qualified"),
        )
        opportunity["next_best_action"], opportunity["next_best_action_reason"] = AcquisitionEngine.get_next_best_action(opportunity)

        await self.db.opportunities.update(org_id, opportunity_id, opportunity)
        await self.events.publish("opportunity_qualified", opportunity)

        return opportunity

    async def personalize(self, org_id: str, opportunity_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run the Personalization Agent."""
        return await self.ai.personalize_opportunity(org_id, opportunity_id, context)

    async def generate_message(self, org_id: str, opportunity_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a message for an opportunity."""
        return await self.ai.generate_message(org_id, opportunity_id, context)

    async def send_message(self, org_id: str, opportunity_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to an opportunity via the infrastructure layer."""
        opportunity = await self.db.opportunities.get(org_id, opportunity_id)
        if not opportunity:
            raise ValueError("Opportunity not found")

        # Delegate to infrastructure integration layer
        # This is the boundary — product layer never touches MTA directly
        send_result = await self.infrastructure.send_message(
            org_id=org_id,
            opportunity_id=opportunity_id,
            from_identity_id=payload.get("from_identity_id"),
            subject=payload.get("subject"),
            body=payload.get("body"),
            channel=payload.get("channel", "email"),
        )

        # Update opportunity state
        opportunity = AcquisitionEngine.transition(
            opportunity,
            OpportunityState.CONTACTED,
            reason="Message sent",
        )
        opportunity["last_contacted_at"] = datetime.utcnow().isoformat()
        opportunity["next_best_action"], opportunity["next_best_action_reason"] = AcquisitionEngine.get_next_best_action(opportunity)

        await self.db.opportunities.update(org_id, opportunity_id, opportunity)
        await self.events.publish("message_sent", opportunity)

        return send_result

    async def get_opportunity(self, org_id: str, opportunity_id: str) -> Optional[Dict[str, Any]]:
        """Get a single opportunity."""
        return await self.db.opportunities.get(org_id, opportunity_id)

    async def list_opportunities(self, org_id: str, filters: Dict[str, Any], pagination: Dict[str, int]) -> tuple[List[Dict[str, Any]], int]:
        """List opportunities with filters and pagination."""
        return await self.db.opportunities.list(org_id, filters, pagination)

    async def get_pipeline(self, org_id: str) -> Dict[str, Any]:
        """Get pipeline view."""
        opportunities, _ = await self.db.opportunities.list(org_id, {}, {"limit": 10000, "offset": 0})

        pipeline = {}
        for state in OpportunityState:
            count = sum(1 for o in opportunities if o.get("state") == state.value)
            value = count * 15000  # Mock average deal value
            pipeline[state.value] = {"count": count, "value": value}

        # Calculate conversion rates
        total_discovered = pipeline.get("discovered", {}).get("count", 1)
        total_qualified = pipeline.get("qualified", {}).get("count", 0)
        total_meetings = pipeline.get("meeting_scheduled", {}).get("count", 0)
        total_opportunities = pipeline.get("opportunity", {}).get("count", 0)

        conversion_rates = {
            "discovered_to_qualified": f"{(total_qualified / total_discovered * 100):.1f}%" if total_discovered > 0 else "0%",
            "qualified_to_meeting": f"{(total_meetings / total_qualified * 100):.1f}%" if total_qualified > 0 else "0%",
            "meeting_to_opportunity": f"{(total_opportunities / total_meetings * 100):.1f}%" if total_meetings > 0 else "0%",
        }

        return {"pipeline": pipeline, "conversion_rates": conversion_rates}

    def _generate_id(self) -> str:
        import uuid
        return uuid.uuid4().hex[:8]
