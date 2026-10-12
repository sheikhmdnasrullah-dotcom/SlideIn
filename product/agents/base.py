"""
Acquisition OS — Base Agent Interface
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime


class AcquisitionAgent(ABC):
    """
    Base class for all AI Acquisition Team agents.
    """

    org_id: str
    config: Dict[str, Any]

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's primary function.
        Returns a structured result with provenance.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        pass


class MockLLMProvider:
    """
    Mock LLM provider for development.
    Replace with real LLM integration (OpenAI, Anthropic, etc.)
    """

    async def complete(self, prompt: str, context: Dict[str, Any]) -> str:
        return f"[MOCK LLM RESPONSE to: {prompt[:50]}...]"


# Global LLM provider instance
llm_provider = MockLLMProvider()
