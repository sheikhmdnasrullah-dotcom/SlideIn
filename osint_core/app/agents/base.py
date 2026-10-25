"""Agent cluster foundation.

`LLMClient` speaks any OpenAI-compatible chat-completions endpoint via env
config (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL). When unconfigured or when a
call fails, agents fall back to their deterministic rule-based path — the
cluster never hard-fails on LLM availability.

`AgentContext` is the typed handoff bundle: raw OSINT outputs in, structured
agent dicts out. Each agent is a pure async callable; the orchestrator
sequences them and emits AI_AGENT_REASONING progress events.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ..events.models import ModuleName
from ..schemas import CompanyIntelligence, InfraRecon, OSINTSideChannel, SocialFootprint, UnifiedDossier


class LLMClient:
    def __init__(self):
        self.base_url = os.getenv("LLM_BASE_URL", "")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "")

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    async def complete_json(self, system: str, user: str, max_tokens: int = 1500) -> dict | None:
        """Returns parsed JSON dict, or None (caller falls back to rules)."""
        if not self.available:
            return None
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "response_format": {"type": "json_object"},
                        "max_tokens": max_tokens,
                        "temperature": 0.4,
                    },
                )
                if resp.status_code != 200:
                    return None
                content = resp.json()["choices"][0]["message"]["content"]
                return json.loads(content)
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            return None


@dataclass
class AgentContext:
    lead_email: str
    parsed: Any                                # ParsedLead
    footprint: SocialFootprint
    infra: InfraRecon
    side: OSINTSideChannel
    dossier: UnifiedDossier                    # tokens pre-built by pipeline
    company: CompanyIntelligence
    mailaccess: dict
    extras: dict = field(default_factory=dict)  # fireenrich/website/blackbird/...
    prior: dict[ModuleName, dict] = field(default_factory=dict)


class NamedAgent(Protocol):
    name: str
    async def run(self, ctx: AgentContext) -> dict: ...
