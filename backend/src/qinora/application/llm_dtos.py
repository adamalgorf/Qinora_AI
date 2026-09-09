"""DTOs for AnalyzeRFQUseCase (application/analyze_rfq.py)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RFQAnalysisRequest(BaseModel):
    document_text: str = Field(min_length=1, description="Raw RFQ document text to analyze")
    reference_spec: str = Field(
        min_length=1, description="Reference specification to compare the RFQ against"
    )


class RFQAnalysisResponse(BaseModel):
    extracted_data: dict[str, Any]
    confidence_score: float = Field(ge=0.0, le=1.0)
    decision_path: list[str]
