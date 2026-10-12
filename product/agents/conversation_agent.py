"""
Acquisition OS — Conversation Agent
Handles authorized replies within strict business rules.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional

from product.agents.base import AcquisitionAgent, llm_provider


class ConversationAgent(AcquisitionAgent):
    """
    Conversation Agent: Handles authorized replies within strict business rules.
    """

    def get_name(self) -> str:
        return "conversation"

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute conversation handling.

        Context:
            - org_id: str
            - conversation_id: str
            - inbound_message: Dict
            - conversation_history: List[Dict]
            - business_policy: Dict
        """
        inbound = context.get("inbound_message", {})
        body = inbound.get("body", "")
        business_policy = context.get("business_policy", {})

        # Classify intent (mock - replace with real LLM classification)
        intent, confidence = self._classify_intent(body)
        signals = self._extract_signals(body, intent)

        # Generate response draft (mock - replace with real LLM generation)
        draft, reasoning, action = self._generate_response(body, intent, business_policy)

        return {
            "agent": self.get_name(),
            "conversation_id": context.get("conversation_id"),
            "response": {
                "draft": draft,
                "intent": intent,
                "confidence": confidence,
                "signals": signals,
                "action": action,  # send, escalate, wait_human
                "reasoning": reasoning,
                "next_best_action": self._suggest_next_action(intent),
            },
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _classify_intent(self, body: str) -> tuple[str, float]:
        body_lower = body.lower()

        if any(word in body_lower for word in ["buy", "purchase", "ready", "interested"]):
            return "buying_signal", 0.9
        elif any(word in body_lower for word in ["not interested", "stop", "unsubscribe"]):
            return "disinterest", 0.85
        elif any(word in body_lower for word in ["question", "?", "how", "what", "when", "why"]):
            return "question", 0.8
        elif any(word in body_lower for word in ["concerned", "worried", "expensive", "can't afford"]):
            return "objection", 0.75
        elif any(word in body_lower for word in ["maybe", "thinking", "considering"]):
            return "neutral", 0.6
        else:
            return "unknown", 0.5

    def _extract_signals(self, body: str, intent: str) -> List[Dict[str, Any]]:
        signals = []
        if intent == "buying_signal":
            signals.append({"type": "buying_signal", "text": body[:200], "confidence": 0.9})
        elif intent == "question":
            signals.append({"type": "question", "text": body[:200], "confidence": 0.8})
        elif intent == "objection":
            signals.append({"type": "objection", "text": body[:200], "confidence": 0.75})
        return signals

    def _generate_response(self, body: str, intent: str, business_policy: Dict) -> tuple[str, str, str]:
        escalation_triggers = business_policy.get("escalate_actions", [])
        forbidden_claims = business_policy.get("forbidden_claims", [])

        # Check escalation triggers
        if any(trigger in body.lower() for trigger in ["underwriting", "approval", "guarantee"]):
            return "", "Escalation required: underwriting question", "escalate"

        # Check forbidden claims
        if any(claim in body.lower() for claim in forbidden_claims):
            return "", "Cannot respond: would make forbidden claim", "escalate"

        # Generate appropriate response
        if intent == "buying_signal":
            draft = "That's great to hear! Would you like to schedule a consultation to discuss your options?"
            reasoning = "Positive buying signal detected; offer consultation"
            action = "send"
        elif intent == "question":
            draft = "Great question! Let me address that for you... [AI-generated response based on general loan concepts]"
            reasoning = "Legitimate question; within policy to answer"
            action = "send"
        elif intent == "objection":
            draft = "I understand your concern. Let me share some information that might help..."
            reasoning = "Objection detected; address with empathy and information"
            action = "send"
        elif intent == "disinterest":
            draft = "I understand. I'll remove you from our outreach. Best of luck with your search!"
            reasoning = "Prospect requested no contact; honor opt-out"
            action = "send"
        else:
            draft = "Thank you for your message. How can I help you today?"
            reasoning = "General inquiry; gather more information"
            action = "send"

        return draft, reasoning, action

    def _suggest_next_action(self, intent: str) -> str:
        if intent == "buying_signal":
            return "send_calendar_link"
        elif intent == "question":
            return "answer_question_then_offer_consultation"
        elif intent == "objection":
            return "address_objection_then_nurture"
        elif intent == "disinterest":
            return "suppress_and_close"
        return "wait_for_response"
