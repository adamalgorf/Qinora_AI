"""Implementations of the CarrierOfferParsingLLM port ("Remy Rates").

StubCarrierOfferParsingLLM is a deterministic, no-credentials fallback: it
always reports low confidence with every field missing, which routes
straight to human review. OpenAICarrierOfferParsingLLM is the real thing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from qinora.application.read_models import ParsedCarrierOfferDraft
from qinora.infrastructure.llm.openai_client import OpenAIStructuredClient, require_openai_api_key
from qinora.infrastructure.settings import Settings

SYSTEM_PROMPT = """You are Remy Rates, an assistant that reads a carrier's (subcontractor's) \
free-text reply to a booking/rate request and extracts a structured offer for the \
Qinora logistics platform.

Rules:
- carrier_name is the company or person the offer is from, as best you can tell from \
the text (e.g. a signature line or introduction). If truly unknown, use an empty string \
and list "carrier_name" in missing_fields.
- price is the carrier's quoted rate as a plain number, with no currency symbol.
- currency should be a 3-letter ISO code (e.g. SEK, EUR, USD) if you can determine it, \
else null.
- transit_days is the number of days the carrier states or implies for transit/pickup, \
as an integer, else null.
- notes should capture any other relevant conditions the carrier mentioned (e.g. \
"subject to space availability"), or null if there are none.
- Only extract facts explicitly present or unambiguously implied by the text. Never \
invent a price, currency, or timeline.
- List every field you could not determine with confidence in missing_fields, using \
the exact field names: carrier_name, price, currency, transit_days.
- confidence must reflect how complete and unambiguous the extraction is: 1.0 only if \
price and carrier are explicit and unambiguous, lower if you had to infer, and low \
(<0.5) if the text is too vague to extract a usable offer from.
"""


class _CarrierOfferSchema(BaseModel):
    carrier_name: str
    price: float | None = None
    currency: str | None = Field(default=None, description="3-letter ISO currency code")
    transit_days: int | None = None
    notes: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class StubCarrierOfferParsingLLM:
    async def parse(self, *, raw_text: str) -> ParsedCarrierOfferDraft:
        _ = raw_text
        return ParsedCarrierOfferDraft(
            carrier_name="",
            price=None,
            currency=None,
            transit_days=None,
            notes=None,
            confidence=0.0,
            missing_fields=("carrier_name", "price", "currency", "transit_days"),
        )


class OpenAICarrierOfferParsingLLM:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def parse(self, *, raw_text: str) -> ParsedCarrierOfferDraft:
        client = OpenAIStructuredClient(
            require_openai_api_key(self._settings), self._settings.openai_model
        )
        result = await client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_text=raw_text,
            schema=_CarrierOfferSchema,
        )
        return ParsedCarrierOfferDraft(
            carrier_name=result.carrier_name,
            price=result.price,
            currency=result.currency,
            transit_days=result.transit_days,
            notes=result.notes,
            confidence=result.confidence,
            missing_fields=tuple(result.missing_fields),
        )
