"""LangChain-backed implementation of the RequestParsingLLM port.

Talks to Azure OpenAI Service (per Qinora's hybrid cloud strategy - AWS as
primary infra, Azure OpenAI as the LLM endpoint for EU data residency).
Only langchain-core (prompts, output parsing) and langchain-openai
(AzureChatOpenAI) are used - not the full `langchain` meta-package, since
this port needs a single structured-output call, not chains/agents/tools.

Nothing outside this module knows LangChain is involved: callers only see
qinora.application.ports.RequestParsingLLM.
"""

from __future__ import annotations

from datetime import datetime

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

from qinora.application.read_models import ParsedCargoLine, ParsedTransportRequestDraft
from qinora.infrastructure.settings import Settings

SYSTEM_PROMPT = """You are Parsek, a transport-request parsing assistant for the \
Qinora logistics platform. Extract a structured transport request from the \
free text the user provides (typically an RFQ or booking email).

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


class LangChainRequestParsingLLM:
    """Azure OpenAI adapter for RequestParsingLLM, built with LangChain.

    Configuration (endpoint/deployment/key) is intentionally read lazily,
    at call time, from Settings - not at construction time. That way the
    container can wire this adapter up even before real Azure OpenAI
    credentials exist (placeholder config), and callers get one clear
    RuntimeError instead of the app failing to start.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._parser = PydanticOutputParser(pydantic_object=_TransportRequestSchema)
        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("human", "{raw_text}\n\n{format_instructions}"),
            ]
        )

    async def parse(self, *, raw_text: str) -> ParsedTransportRequestDraft:
        model = self._build_model()
        chain = self._prompt | model | self._parser
        result: _TransportRequestSchema = await chain.ainvoke(
            {
                "raw_text": raw_text,
                "format_instructions": self._parser.get_format_instructions(),
            }
        )
        return _to_draft(result)

    def _build_model(self) -> AzureChatOpenAI:
        settings = self._settings
        if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=azure_openai but Azure OpenAI is not configured. "
                "Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and "
                "AZURE_OPENAI_DEPLOYMENT (see .env.example), or set "
                "LLM_PROVIDER=stub to use the deterministic fallback."
            )
        if not settings.azure_openai_deployment:
            raise RuntimeError(
                "AZURE_OPENAI_DEPLOYMENT is required when LLM_PROVIDER=azure_openai."
            )

        return AzureChatOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            azure_deployment=settings.azure_openai_deployment,
            api_version=settings.azure_openai_api_version,
            temperature=0,
        )


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
