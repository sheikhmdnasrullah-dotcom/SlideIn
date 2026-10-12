"""
Acquisition OS — Acquisition Engine Service
Core pipeline engine with real state transitions and event publishing.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

from product.api.schemas import OpportunityState
from product.db.models import OpportunityEvent
from product.events import EventBus, EventTypes


class AcquisitionEngine:
    """
    Core finite-state machine for opportunity lifecycle.
    """

    TRANSITIONS = {
        OpportunityState.DISCOVERED: [OpportunityState.RESEARCHED, OpportunityState.DISQUALIFIED],
        OpportunityState.RESEARCHED: [OpportunityState.QUALIFIED, OpportunityState.DISQUALIFIED],
        OpportunityState.QUALIFIED: [OpportunityState.CONTACTED, OpportunityState.NURTURING],
        OpportunityState.CONTACTED: [OpportunityState.ENGAGED, OpportunityState.NURTURING],
        OpportunityState.ENGAGED: [OpportunityState.INTENT_DETECTED, OpportunityState.NURTURING],
        OpportunityState.INTENT_DETECTED: [OpportunityState.BOOKING, OpportunityState.ENGAGED, OpportunityState.NURTURING],
        OpportunityState.BOOKING: [OpportunityState.MEETING_SCHEDULED, OpportunityState.ENGAGED],
        OpportunityState.MEETING_SCHEDULED: [OpportunityState.MEETING_COMPLETED, OpportunityState.BOOKING],
        OpportunityState.MEETING_COMPLETED: [OpportunityState.OPPORTUNITY, OpportunityState.NURTURING],
        OpportunityState.OPPORTUNITY: [OpportunityState.CUSTOMER],
        OpportunityState.CUSTOMER: [],
        OpportunityState.COOLING: [OpportunityState.NURTURING, OpportunityState.DISQUALIFIED],
        OpportunityState.NURTURING: [OpportunityState.ENGAGED, OpportunityState.DISQUALIFIED],
        OpportunityState.DISQUALIFIED: [],
    }

    @classmethod
    def can_transition(cls, from_state: OpportunityState, to_state: OpportunityState) -> bool:
        return to_state in cls.TRANSITIONS.get(from_state, [])

    @classmethod
    def transition(
        cls,
        opportunity: Dict[str, Any],
        to_state: OpportunityState,
        reason: Optional[str] = None,
        org_id: Optional[str] = None,
        event_bus: Optional[EventBus] = None,
    ) -> Dict[str, Any]:
        """Attempt a state transition."""
        current_state = opportunity.get("state")
        current_state_enum = OpportunityState(current_state) if current_state else OpportunityState.DISCOVERED

        if not cls.can_transition(current_state_enum, to_state):
            raise ValueError(
                f"Cannot transition from {current_state} to {to_state.value}. "
                f"Valid next states: {[s.value for s in cls.TRANSITIONS.get(current_state_enum, [])]}"
            )

        now = datetime.utcnow().isoformat()
        lifecycle = opportunity.get("lifecycle", {})
        state_history = lifecycle.get("state_history", [])

        # Close current state
        if state_history:
            state_history[-1]["exited_at"] = now
            state_history[-1]["reason"] = reason

        # Enter new state
        state_history.append({
            "state": to_state.value,
            "entered_at": now,
            "exited_at": None,
            "reason": reason,
        })

        opportunity["state"] = to_state.value
        opportunity["lifecycle"] = {
            **lifecycle,
            "state": to_state.value,
            "state_history": state_history,
        }
        opportunity["updated_at"] = now
        opportunity["version"] = opportunity.get("version", 1) + 1

        # Publish event
        if event_bus and org_id:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(event_bus.publish(
                    EventTypes.OPPORTUNITY_STATE_CHANGED,
                    {
                        "id": opportunity.get("id"),
                        "from_state": current_state,
                        "to_state": to_state.value,
                        "reason": reason,
                    },
                    org_id,
                ))
            except RuntimeError:
                pass

        return opportunity

    @classmethod
    def get_next_best_action(cls, opportunity: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """Determine the next best action based on opportunity state and signals."""
        state = opportunity.get("state")
        intent = opportunity.get("intent", {})
        qualification = opportunity.get("qualification", {})

        actions = {
            OpportunityState.DISCOVERED: ("research_opportunity", "New opportunity discovered; research to build profile"),
            OpportunityState.RESEARCHED: ("qualify_opportunity", "Research complete; qualify against ICP"),
            OpportunityState.QUALIFIED: ("send_qualification_questionnaire", "Qualified; gather more information"),
            OpportunityState.CONTACTED: ("follow_up", "Message sent; await response"),
            OpportunityState.ENGAGED: (
                "book_consultation" if intent.get("level") == "high" else "nurture",
                "High intent detected; move to booking" if intent.get("level") == "high" else "Engaged; continue nurture sequence",
            ),
            OpportunityState.INTENT_DETECTED: ("send_calendar_link", "Strong intent; offer consultation"),
            OpportunityState.BOOKING: ("confirm_meeting", "Calendar sent; confirm meeting"),
            OpportunityState.MEETING_SCHEDULED: ("prepare_for_meeting", "Meeting scheduled; prepare materials"),
            OpportunityState.MEETING_COMPLETED: ("create_opportunity", "Meeting complete; create loan opportunity"),
            OpportunityState.NURTURING: ("send_value_content", "Not ready; provide useful content"),
            OpportunityState.COOLING: ("re_engage_or_disqualify", "Cooling; decide whether to re-engage or disqualify"),
        }

        return actions.get(state, (None, None))
