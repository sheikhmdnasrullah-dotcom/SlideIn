"""
Acquisition OS — Command Center Service
Business logic for the Command Center.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from product.services.acquisition_engine import AcquisitionEngine


class CommandCenterService:
    """Service layer for the Command Center."""

    def __init__(self, db_repository, event_publisher, opportunity_service, ai_orchestrator):
        self.db = db_repository
        self.events = event_publisher
        self.opportunity_service = opportunity_service
        self.ai = ai_orchestrator

    async def get_command_center(self, org_id: str, user_id: str) -> Dict[str, Any]:
        """Get Command Center data."""

        # Get overnight summary
        overnight_summary = await self._get_overnight_summary(org_id)

        # Get today's priorities
        todays_priorities = await self._get_todays_priorities(org_id, user_id)

        # Get system activity
        system_activity = await self._get_system_activity(org_id)

        return {
            "greeting": self._get_greeting(),
            "overnight_summary": overnight_summary,
            "todays_priorities": todays_priorities,
            "system_activity": system_activity,
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def execute_command(self, org_id: str, user_id: str, command: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a natural language command."""

        command_lower = command.lower()

        # Simple command routing (replace with real LLM-based interpretation)
        if any(phrase in command_lower for phrase in ["high-intent", "high intent", "strong intent"]):
            return await self._handle_high_intent_command(org_id, user_id, command)
        elif "conversation" in command_lower and "attention" in command_lower:
            return await self._handle_conversations_attention_command(org_id, user_id, command)
        elif "campaign" in command_lower:
            return await self._handle_campaign_command(org_id, user_id, command)
        elif "content" in command_lower:
            return await self._handle_content_command(org_id, user_id, command)
        elif "pause" in command_lower:
            return await self._handle_pause_command(org_id, user_id, command)
        else:
            return {
                "command": command,
                "interpreted": {"intent": "unknown", "raw": command},
                "results": [],
                "suggestions": [
                    "Show me high-intent borrowers from this week",
                    "Show me conversations that need my attention",
                    "Find the five strongest opportunities that haven't been contacted",
                ],
            }

    async def _get_overnight_summary(self, org_id: str) -> Dict[str, int]:
        """Get overnight activity summary."""
        # In production, query real event data
        return {
            "new_opportunities_discovered": 12,
            "high_fit_prospects_researched": 4,
            "active_conversations": 7,
            "strong_intent_prospects": 2,
            "meetings_booked": 1,
            "cooling_opportunities": 3,
        }

    async def _get_todays_priorities(self, org_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Get today's action priorities."""
        # In production, query real opportunities needing action
        return [
            {
                "rank": 1,
                "opportunity_id": "opp_demo_3",
                "name": "Emily Davis",
                "state": "ready_to_discuss_financing",
                "action": "review_conversation",
                "reason": "Strong purchase intent + active conversation + defined timeframe",
            },
            {
                "rank": 2,
                "opportunity_id": "opp_demo_2",
                "name": "Mike Chen",
                "state": "asked_about_refinance",
                "action": "review_ai_response",
                "reason": "AI drafted response to refinance question; awaiting approval",
            },
            {
                "rank": 3,
                "opportunity_id": None,
                "name": "4 prospects",
                "state": "high_fit_not_contacted",
                "action": "review_outreach",
                "reason": "Research complete; awaiting your review",
            },
        ]

    async def _get_system_activity(self, org_id: str) -> List[Dict[str, Any]]:
        """Get recent system activity."""
        # In production, query real system_activities table
        return [
            {
                "type": "content_published",
                "description": "Published today's article",
                "timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
            },
            {
                "type": "content_generated",
                "description": "Generated LinkedIn post",
                "timestamp": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            },
            {
                "type": "automation_triggered",
                "description": "Updated calculator funnel",
                "timestamp": (datetime.utcnow() - timedelta(minutes=45)).isoformat(),
            },
            {
                "type": "opportunity_state_changed",
                "description": "Followed up with 8 opportunities",
                "timestamp": (datetime.utcnow() - timedelta(minutes=30)).isoformat(),
            },
            {
                "type": "high_intent_detected",
                "description": "Detected 2 new buying signals",
                "timestamp": (datetime.utcnow() - timedelta(minutes=15)).isoformat(),
            },
        ]

    def _get_greeting(self) -> str:
        """Get time-appropriate greeting."""
        hour = datetime.utcnow().hour
        if hour < 12:
            return "Good morning"
        elif hour < 17:
            return "Good afternoon"
        else:
            return "Good evening"

    async def _handle_high_intent_command(self, org_id: str, user_id: str, command: str) -> Dict[str, Any]:
        """Handle high-intent prospects command."""
        return {
            "command": command,
            "interpreted": {
                "intent": "list_opportunities",
                "filters": {"state": "intent_detected"},
            },
            "results": [
                {"opportunity_id": "opp_demo_3", "name": "Emily Davis", "score": 91, "state": "booking"},
                {"opportunity_id": "opp_demo_1", "name": "Sarah Johnson", "score": 85, "state": "engaged"},
            ],
            "suggestions": [
                "Show me conversations that need my attention",
                "Find the five strongest opportunities that haven't been contacted",
            ],
        }

    async def _handle_conversations_attention_command(self, org_id: str, user_id: str, command: str) -> Dict[str, Any]:
        """Handle conversations needing attention command."""
        return {
            "command": command,
            "interpreted": {
                "intent": "list_conversations_needing_attention",
                "filters": {"state": "active"},
            },
            "results": [
                {"conversation_id": "conv_1", "opportunity_id": "opp_demo_3", "name": "Emily Davis", "reason": "Awaiting calendar link"},
            ],
            "suggestions": [
                "Show me high-intent borrowers from this week",
                "Create a campaign for first-time buyers in Austin",
            ],
        }

    async def _handle_campaign_command(self, org_id: str, user_id: str, command: str) -> Dict[str, Any]:
        """Handle campaign command."""
        return {
            "command": command,
            "interpreted": {
                "intent": "create_campaign",
                "params": {"segment": "first_time_buyer", "location": "Austin, TX"},
            },
            "results": [],
            "suggestions": [
                "Show me what worked best last month",
                "Prepare tomorrow's content",
            ],
        }

    async def _handle_content_command(self, org_id: str, user_id: str, command: str) -> Dict[str, Any]:
        """Handle content command."""
        return {
            "command": command,
            "interpreted": {
                "intent": "generate_content",
                "params": {"topic": "down_payment_assistance"},
            },
            "results": [
                {"content_id": "content_1", "title": "Austin First-Time Buyer's Guide to Down Payment Assistance", "type": "article"},
            ],
            "suggestions": [
                "Publish the content to LinkedIn",
                "Create a lead magnet from this article",
            ],
        }

    async def _handle_pause_command(self, org_id: str, user_id: str, command: str) -> Dict[str, Any]:
        """Handle pause command."""
        return {
            "command": command,
            "interpreted": {
                "intent": "pause_automated_conversations",
                "params": {"pause_all": True},
            },
            "results": [],
            "suggestions": [
                "Resume automated conversations",
                "Show me paused automations",
            ],
        }
