"""Shared helper for narrow, structured-output OpenAI calls.

Every agent adapter in this package sends one small, focused prompt and a
Pydantic schema and gets back a validated object - no chat history, no tool
loop, no framework. Keeping each call this narrow (rather than one big
agent that has to be told about every possible job on every request) is
what keeps token usage, and therefore cost, low.
"""

from __future__ import annotations

from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from qinora.infrastructure.settings import Settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def require_openai_api_key(settings: Settings) -> str:
    if not settings.openai_api_key:
        raise RuntimeError(
            "LLM_PROVIDER=openai but OPENAI_API_KEY is not set. "
            "Set OPENAI_API_KEY (see .env.example), or set LLM_PROVIDER=stub "
            "to use the deterministic fallback."
        )
    return settings.openai_api_key


class OpenAIStructuredClient:
    """Thin wrapper around one narrow OpenAI structured-output call."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(
        self,
        *,
        system_prompt: str,
        user_text: str,
        schema: type[SchemaT],
    ) -> SchemaT:
        response = await self._client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            response_format=schema,
            temperature=0,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("OpenAI response did not include parsed structured output")
        return parsed
