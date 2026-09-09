"""Port for LLM-backed multi-step workflows.

Application code (e.g. application/analyze_rfq.py) depends only on
GraphExecutor and never imports a model client directly - see
infrastructure/llm/graph_executor.py for the stub (default, no credentials)
and OpenAI implementations.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    """Structured input to a graph-based LLM workflow.

    `input_data` carries the caller's structured Pydantic input as a plain
    dict, so this port stays independent of any one use case's schema.
    """

    prompt: str
    input_data: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """Structured output from a graph-based LLM workflow, including the
    sequence of graph nodes it visited so the reasoning stays visible to
    callers (see RFQAnalysisResponse.decision_path).
    """

    output_data: dict[str, Any]
    decision_path: list[str] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0, default=1.0)


class GraphExecutor(Protocol):
    """Runs a multi-step graph workflow over an LLMRequest and returns a
    validated LLMResponse.
    """

    async def run(self, request: LLMRequest) -> LLMResponse:
        pass
