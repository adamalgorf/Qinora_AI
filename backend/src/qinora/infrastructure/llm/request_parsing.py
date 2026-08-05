"""Implementations of the RequestParsingLLM port ("Parsek").

StubRequestParsingLLM is a deterministic, no-credentials fallback: it
always reports low confidence with every field missing, which routes
straight to human review rather than silently creating requests from
unparsed text. OpenAIRequestParsingLLM is the real thing.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from qinora.application.read_models import ParsedCargoLine, ParsedTransportRequestDraft
from qinora.infrastructure.llm.openai_client import OpenAIStructuredClient, require_openai_api_key
from qinora.infrastructure.settings import Settings

SYSTEM_PROMPT = """You are Parsek, a transport-request parsing assistant for the \
Qinora logistics platform. Extract a structured transport request from the \
free text the user provides (typically an RFQ or booking email from a customer).

Rules:
- mode must be exactly one of: ftl, ltl, ocean, air, rail, intermodal.
- Only extract facts explicitly present or unambiguously implied by the text. \
Never invent weights, dimensions, dates, or addresses.
- List every field you could not determine with confidence in missing_fields, \
using the exact field names: mode, origin, destination, cargo, loading_time, \
unloading_time, cargo.weight_kg, cargo.dimensions.
- confidence must reflect how complete and unambiguous the extraction is: \
1.0 only if every required field is explicit and unambiguous, lower if you \
had to infer, and low (<0.5) if the text is too vague to parse reliably.
- loading_time / unloading_time must be ISO 8601 datetimes, or null if unknown.
"""


class _CargoLineSchema(BaseModel):
    description: str
    quantity: int | None = None
    weight_kg: float | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None


class _TransportRequestSchema(BaseModel):
    mode: str = Field(description="One of: ftl, ltl, ocean, air, rail, intermodal")
    origin: str
    destination: str
    cargo: list[_CargoLineSchema] = Field(default_factory=list)
    loading_time: str | None = Field(default=None, description="ISO 8601 datetime, or null")
    unloading_time: str | None = Field(default=None, description="ISO 8601 datetime, or null")
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class StubRequestParsingLLM:
    async def parse(self, *, raw_text: str) -> ParsedTransportRequestDraft:
        _ = raw_text
        return ParsedTransportRequestDraft(
            mode="ftl",
            origin="",
            destination="",
            cargo=(),
            loading_time=None,
            unloading_time=None,
            confidence=0.0,
            missing_fields=(
                "mode",
                "origin",
                "destination",
                "cargo",
                "loading_time",
                "unloading_time",
            ),
        )


class OpenAIRequestParsingLLM:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def parse(self, *, raw_text: str) -> ParsedTransportRequestDraft:
        client = OpenAIStructuredClient(
            require_openai_api_key(self._settings), self._settings.openai_model
        )
        result = await client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_text=raw_text,
            schema=_TransportRequestSchema,
        )
        return _to_draft(result)


def _to_draft(schema: _TransportRequestSchema) -> ParsedTransportRequestDraft:
    return ParsedTransportRequestDraft(
        mode=schema.mode,
        origin=schema.origin,
        destination=schema.destination,
        cargo=tuple(
            ParsedCargoLine(
                description=line.description,
                quantity=line.quantity,
                weight_kg=line.weight_kg,
                length_cm=line.length_cm,
                width_cm=line.width_cm,
                height_cm=line.height_cm,
            )
            for line in schema.cargo
        ),
        loading_time=_parse_datetime(schema.loading_time),
        unloading_time=_parse_datetime(schema.unloading_time),
        confidence=schema.confidence,
        missing_fields=tuple(schema.missing_fields),
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
