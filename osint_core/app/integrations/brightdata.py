"""BrightData AI Lead Matrix adapter — B2B company/leadership/funding schemas.

BrightData is a commercial dataset API. This adapter speaks its
dataset-endpoint shape over plain HTTPS and degrades to an empty stub when no
API key is configured, so the pipeline contract never changes.

Env: BRIGHTDATA_API_KEY, BRIGHTDATA_ENDPOINT (defaults to the dataset
collection endpoint; override for your contract).
"""
from __future__ import annotations

import json
import os

from ..core.transport import Ja3Transport, Ja3ProbeError
from ..schemas import CompanyIntelligence

DEFAULT_ENDPOINT = "https://api.brightdata.com/datasets/v3/trigger"


class BrightDataAdapter:
    def __init__(self, transport: Ja3Transport):
        self._transport = transport
        self._key = os.getenv("BRIGHTDATA_API_KEY")
        self._endpoint = os.getenv("BRIGHTDATA_ENDPOINT", DEFAULT_ENDPOINT)

    async def enrich_company(self, domain: str, on_unit=None) -> CompanyIntelligence:
        if not self._key:
            return CompanyIntelligence(domain=domain, confidence=0.0)

        body = json.dumps([{"domain": domain}])
        try:
            status, text = await self._transport.get(
                f"{self._endpoint}?dataset=company_lead_matrix",
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                },
            )
        except Ja3ProbeError:
            return CompanyIntelligence(domain=domain, confidence=0.0)

        try:
            data = json.loads(text)
        except ValueError:
            return CompanyIntelligence(domain=domain, confidence=0.0)

        if isinstance(data, list) and data:
            data = data[0]

        if on_unit:
            await on_unit({"company": data.get("name", domain)})

        leadership = [
            {
                "name": p.get("name"),
                "title": p.get("job_title") or p.get("title"),
                "linkedin": p.get("linkedin_url"),
            }
            for p in (data.get("leadership") or data.get("people") or [])
        ][:10]

        funding = data.get("funding") or {}
        return CompanyIntelligence(
            name=data.get("name") or data.get("company_name"),
            domain=domain,
            industry=data.get("industry"),
            size_band=data.get("size") or data.get("employee_count"),
            funding_stage=funding.get("stage") or data.get("funding_stage"),
            total_funding=funding.get("total") or data.get("total_funding"),
            leadership=leadership,
            tech_stack=data.get("technologies") or [],
            confidence=0.85,
        )
