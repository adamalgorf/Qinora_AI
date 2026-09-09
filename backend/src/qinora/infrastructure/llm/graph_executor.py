"""Implementations of the GraphExecutor port ("analyze RFQ" graph).

StubGraphExecutor is a deterministic, no-credentials fallback: it walks the
same extract -> compare -> recommend node sequence without calling any
model, and always reports zero confidence so it can never be mistaken for a
real analysis. OpenAIGraphExecutor is the real thing - the same three
sequential structured OpenAI calls as the other agents in this package
(Parsek, Remy Rates, Rex Response), no extra framework required.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from qinora.application.llm_ports import LLMRequest, LLMResponse
from qinora.infrastructure.llm.openai_client import OpenAIStructuredClient, require_openai_api_key
from qinora.infrastructure.settings import Settings

NODE_EXTRACT = "extract"
NODE_COMPARE = "compare"
NODE_RECOMMEND = "recommend"


class StubGraphExecutor:
    """Always returns a fixed, obviously-synthetic result at zero
    confidence, so it's unmistakable in development before OPENAI_API_KEY
    is configured.
    """

    async def run(self, request: LLMRequest) -> LLMResponse:
        document_text = request.input_data.get("document_text", "")
        reference_spec = request.input_data.get("reference_spec", "")

        return LLMResponse(
            output_data={
                "extracted": {"summary": "", "fields": {}, "raw_length": len(document_text)},
                "comparison": {
                    "matches_reference": False,
                    "differences": [],
                    "reference_length": len(reference_spec),
                },
                "recommendation": {
                    "decision": "needs_human_review",
                    "reason": "stub adapter - no LLM configured",
                },
            },
            decision_path=[NODE_EXTRACT, NODE_COMPARE, NODE_RECOMMEND],
            confidence_score=0.0,
        )


EXTRACT_SYSTEM_PROMPT = """You are an RFQ analysis assistant for the Qinora \
logistics platform. Extract the key fields and a one-paragraph summary from \
the RFQ document text you're given. Only extract facts explicitly present; \
never invent details."""

COMPARE_SYSTEM_PROMPT = """You are an RFQ analysis assistant. Compare the \
extracted RFQ fields against the reference specification you're given, and \
list any differences you find. matches_reference is true only if there are \
no material differences."""

RECOMMEND_SYSTEM_PROMPT = """You are an RFQ analysis assistant. Given the \
extraction and comparison you're given, recommend approve / reject / \
needs_human_review with a short reason. confidence must reflect how \
certain you are: 1.0 only if the recommendation is unambiguous, lower if \
you had to make judgment calls, and low (<0.5) if the input was too thin \
or contradictory to decide reliably."""


class _ExtractedFields(BaseModel):
    summary: str
    fields: dict[str, str] = Field(default_factory=dict)


class _Comparison(BaseModel):
    matches_reference: bool
    differences: list[str] = Field(default_factory=list)


class _Recommendation(BaseModel):
    decision: Literal["approve", "reject", "needs_human_review"]
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class OpenAIGraphExecutor:
    """Runs extract -> compare -> recommend as three sequential structured
    OpenAI calls via OpenAIStructuredClient, threading each step's output
    into the next and recording decision_path as it goes.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self, request: LLMRequest) -> LLMResponse:
        document_text = request.input_data.get("document_text", request.prompt)
        reference_spec = request.input_data.get("reference_spec", "")
        client = OpenAIStructuredClient(
            require_openai_api_key(self._settings), self._settings.openai_model
        )
        decision_path: list[str] = []

        extracted = await client.complete(
            system_prompt=EXTRACT_SYSTEM_PROMPT,
            user_text=document_text,
            schema=_ExtractedFields,
        )
        decision_path.append(NODE_EXTRACT)

        comparison = await client.complete(
            system_prompt=COMPARE_SYSTEM_PROMPT,
            user_text=f"Extracted: {extracted.model_dump()}\n\nReference spec:\n{reference_spec}",
            schema=_Comparison,
        )
        decision_path.append(NODE_COMPARE)

        recommendation = await client.complete(
            system_prompt=RECOMMEND_SYSTEM_PROMPT,
            user_text=(
                f"Extracted: {extracted.model_dump()}\n\nComparison: {comparison.model_dump()}"
            ),
            schema=_Recommendation,
        )
        decision_path.append(NODE_RECOMMEND)

        return LLMResponse(
            output_data={
                "extracted": extracted.model_dump(),
                "comparison": comparison.model_dump(),
                "recommendation": recommendation.model_dump(),
            },
            decision_path=decision_path,
            confidence_score=recommendation.confidence,
        )
