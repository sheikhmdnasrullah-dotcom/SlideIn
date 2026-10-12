"""
Acquisition OS — Real LLM Integration
Wraps OpenAI/Anthropic for the AI Acquisition Team.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMProvider:
    """
    LLM provider abstraction.
    Supports OpenAI and Anthropic with automatic fallback.
    """

    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.provider = None

        if self.openai_api_key:
            self.provider = "openai"
        elif self.anthropic_api_key:
            self.provider = "anthropic"
        else:
            self.provider = "mock"
            logger.warning("No LLM API key found. Using mock LLM responses.")

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        context: Dict[str, Any] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        """Complete a prompt with the LLM."""
        if self.provider == "openai":
            return await self._openai_complete(system_prompt, user_prompt, temperature, max_tokens)
        elif self.provider == "anthropic":
            return await self._anthropic_complete(system_prompt, user_prompt, temperature, max_tokens)
        else:
            return self._mock_complete(user_prompt)

    async def _openai_complete(self, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> str:
        """OpenAI completion."""
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=self.openai_api_key)

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI completion failed: {e}")
            return self._mock_complete(user_prompt)

    async def _anthropic_complete(self, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> str:
        """Anthropic completion."""
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=self.anthropic_api_key)

            response = await client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt},
                ],
            )

            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Anthropic completion failed: {e}")
            return self._mock_complete(user_prompt)

    def _mock_complete(self, user_prompt: str) -> str:
        """Mock completion for development."""
        return f"[MOCK LLM RESPONSE to: {user_prompt[:50]}...]"


# Global LLM provider instance
llm_provider = LLMProvider()
