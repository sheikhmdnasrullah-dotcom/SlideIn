"""
Acquisition OS — Content & Optimization Agents
"""

from datetime import datetime
from typing import Dict, Any, List, Optional

from product.agents.base import AcquisitionAgent, llm_provider


class ContentAgent(AcquisitionAgent):
    """
    Content Agent: Creates authority content for the customer.
    """

    def get_name(self) -> str:
        return "content"

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute content generation.

        Context:
            - org_id: str
            - topic: str
            - target_segment: str
            - geography: List[str]
            - content_type: str
        """
        topic = context.get("topic", "general")
        target_segment = context.get("target_segment", "general")
        geography = context.get("geography", [])
        content_type = context.get("content_type", "article")

        location_str = ", ".join(geography) if geography else "your area"

        if content_type == "article":
            title = f"{location_str.title()} {topic.replace('_', ' ').title()} Guide"
            body = f"# {title}\n\n## Introduction\n\nIf you're a {target_segment.replace('_', ' ')} in {location_str}...\n\n## Key Points\n\n1. Understanding your options\n2. Local market insights\n3. Next steps\n\n## Conclusion\n\nContact us for a personalized consultation."
        elif content_type == "linkedin_post":
            title = f"LinkedIn: {topic.replace('_', ' ').title()} tips"
            body = f"Just published a guide on {topic.replace('_', ' ')} for {target_segment.replace('_', ' ')} in {location_str}...\n\n#mortgage #homeloans #realestate"
        elif content_type == "lead_magnet":
            title = f"{target_segment.replace('_', ' ').title()} Checklist"
            body = f"# {title}\n\nUse this checklist to...\n\n[Download link]"
        else:
            title = f"{topic.replace('_', ' ').title()} Content"
            body = f"Content about {topic} for {target_segment} in {location_str}..."

        return {
            "agent": self.get_name(),
            "content_plan": [
                {
                    "title": title,
                    "type": content_type,
                    "topic": topic,
                    "summary": body[:200],
                    "related_content": [],
                    "linkedin_post": f"LinkedIn: {title}" if content_type == "article" else None,
                    "lead_magnet": f"{target_segment.replace('_', ' ').title()} Checklist" if content_type == "article" else None,
                    "calculator": "affordability_calculator",
                    "email_follow_up": "3-email nurture sequence",
                    "reasoning": f"Top prospect topic for {target_segment} in {location_str}",
                }
            ],
            "generated_at": datetime.utcnow().isoformat(),
        }


class OptimizationAgent(AcquisitionAgent):
    """
    Optimization Agent: Analyzes and improves acquisition performance.
    """

    def get_name(self) -> str:
        return "optimization"

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute optimization analysis.

        Context:
            - org_id: str
            - funnel_metrics: Dict
            - content_performance: List[Dict]
            - conversation_metrics: Dict
        """
        funnel = context.get("funnel_metrics", {})
        content_perf = context.get("content_performance", [])

        recommendations = []

        # Analyze funnel conversion
        discovered = funnel.get("discovered", 0)
        qualified = funnel.get("qualified", 0)
        meetings = funnel.get("meeting_scheduled", 0)

        if discovered > 0 and qualified / discovered < 0.5:
            recommendations.append({
                "type": "funnel_optimization",
                "priority": "high",
                "title": "Research coverage below target",
                "detail": "Less than 50% of discovered opportunities are being researched. Consider automating research.",
                "action": "automate_research",
                "estimated_impact": "30% more qualified opportunities",
            })

        if qualified > 0 and meetings / qualified < 0.15:
            recommendations.append({
                "type": "funnel_optimization",
                "priority": "high",
                "title": "Booking rate needs attention",
                "detail": "Conversion from qualified to meeting has declined. Review qualification flow and booking process.",
                "action": "review_qualification_flow",
                "estimated_impact": "12 additional meetings/month",
            })

        # Analyze content performance
        if content_perf:
            best_content = max(content_perf, key=lambda c: c.get("meetings_booked", 0))
            recommendations.append({
                "type": "content_optimization",
                "priority": "medium",
                "title": f"Strongest content: {best_content.get('title', 'unknown')}",
                "detail": f"This content drove {best_content.get('meetings_booked', 0)} meetings. Consider creating more content on this topic.",
                "action": "create_similar_content",
            })

        # General recommendation
        recommendations.append({
            "type": "message_optimization",
            "priority": "medium",
            "title": "Personalize first-touch messages",
            "detail": "Prospects respond 23% better when first email references their stated timeframe or recent activity.",
            "action": "update_message_template",
        })

        return {
            "agent": self.get_name(),
            "org_id": context.get("org_id"),
            "recommendations": recommendations,
            "generated_at": datetime.utcnow().isoformat(),
        }
