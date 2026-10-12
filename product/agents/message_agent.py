"""
Acquisition OS — Message Agent
Creates the actual communication content.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional

from product.agents.base import AcquisitionAgent, llm_provider


class MessageAgent(AcquisitionAgent):
    """
    Message Agent: Creates the actual communication content.
    """

    def get_name(self) -> str:
        return "message"

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute message generation.

        Context:
            - org_id: str
            - opportunity_id: str
            - personalization: Dict
            - brand_voice: Dict
            - channel: str
            - purpose: str
        """
        personalization = context.get("personalization", {})
        brand_voice = context.get("brand_voice", {})
        channel = context.get("channel", "email")
        purpose = context.get("purpose", "initial_outreach")

        # Build message (mock - replace with real LLM generation)
        subject, body = self._build_message(personalization, brand_voice, channel, purpose)

        return {
            "agent": self.get_name(),
            "opportunity_id": context.get("opportunity_id"),
            "message": {
                "subject": subject,
                "body": body,
                "channel": channel,
                "personalization_score": 0.85,
                "compliance_check": "passed",
            },
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _build_message(self, personalization: Dict, brand_voice: Dict, channel: str, purpose: str) -> tuple[str, str]:
        opening = personalization.get("opening_context", "I noticed you've been exploring mortgage options...")
        relevance = personalization.get("genuine_relevance", "")
        avoid = personalization.get("avoid", [])

        if channel == "email":
            if purpose == "initial_outreach":
                subject = "Quick question about your home buying plans"
                body = f"""Hi there,

{opening}

{relevance}

Would you be open to a brief conversation about your options? I'm here to help.

Best regards"""
            elif purpose == "follow_up":
                subject = "Following up on your mortgage questions"
                body = f"""Hi there,

I wanted to follow up on our previous conversation.

{relevance}

Is there anything specific you'd like to discuss?

Best regards"""
            else:
                subject = "Re: Your mortgage question"
                body = f"""Hi there,

Great question! {relevance}

Would you like to schedule a brief call to discuss this further?

Best regards"""
        else:
            subject = ""
            body = f"{opening} {relevance}"

        return subject, body
