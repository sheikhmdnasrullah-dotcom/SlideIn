"""
Acquisition OS — Health Service
Business logic for Acquisition Health metrics.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any

from product.api.schemas import HealthMetricSchema


class HealthService:
    """Service layer for acquisition health metrics."""

    def __init__(self, db_repository, opportunity_service, content_service):
        self.db = db_repository
        self.opportunity_service = opportunity_service
        self.content_service = content_service

    async def get_acquisition_health(self, org_id: str) -> Dict[str, Any]:
        """Get acquisition health metrics."""
        # In production, calculate from real data
        metrics = [
            HealthMetricSchema(
                metric="lead_flow",
                status="excellent",
                value=45.0,
                target=30.0,
                trend="up",
                detail="12 new opportunities discovered this week",
            ),
            HealthMetricSchema(
                metric="research_coverage",
                status="good",
                value=75.0,
                target=80.0,
                trend="stable",
                detail="75% of new opportunities have been researched",
            ),
            HealthMetricSchema(
                metric="conversation_health",
                status="excellent",
                value=88.0,
                target=75.0,
                trend="up",
                detail="Active conversations showing strong engagement",
            ),
            HealthMetricSchema(
                metric="booking_rate",
                status="needs_attention",
                value=8.5,
                target=15.0,
                trend="down",
                detail="Conversion from qualified conversation to booked meeting has declined 18%",
            ),
            HealthMetricSchema(
                metric="content_performance",
                status="excellent",
                value=92.0,
                target=80.0,
                trend="up",
                detail="Content driving strong inbound lead flow",
            ),
            HealthMetricSchema(
                metric="email_deliverability",
                status="excellent",
                value=97.0,
                target=90.0,
                trend="stable",
                detail="Primary inbox rate within target range",
            ),
        ]

        recommendation = (
            "Your calculator is generating leads normally, but the conversion from "
            "qualified conversation to booked meeting has declined 18%. The strongest "
            "drop occurs after the first qualification question. Review the qualification flow."
        )

        return {
            "org_id": org_id,
            "metrics": metrics,
            "recommendation": recommendation,
            "generated_at": datetime.utcnow().isoformat(),
        }
