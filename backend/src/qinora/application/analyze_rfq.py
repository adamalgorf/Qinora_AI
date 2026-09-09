"""AnalyzeRFQUseCase - extracts structured data from an RFQ document,
compares it against a reference spec, and recommends a decision, by running
the extract -> compare -> recommend steps behind the GraphExecutor port. See
infrastructure/llm/graph_executor.py for the stub and OpenAI implementations
of that sequence.
"""

from __future__ import annotations

from dataclasses import dataclass

from qinora.application.llm_dtos import RFQAnalysisRequest, RFQAnalysisResponse
from qinora.application.llm_ports import GraphExecutor, LLMRequest


@dataclass
class AnalyzeRFQUseCase:
    graph_executor: GraphExecutor

    async def execute(self, request: RFQAnalysisRequest) -> RFQAnalysisResponse:
        llm_request = LLMRequest(
            prompt=request.document_text,
            input_data={
                "document_text": request.document_text,
                "reference_spec": request.reference_spec,
            },
        )
        result = await self.graph_executor.run(llm_request)
        return RFQAnalysisResponse(
            extracted_data=result.output_data,
            confidence_score=result.confidence_score,
            decision_path=result.decision_path,
        )
