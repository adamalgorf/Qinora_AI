"""Implementations of the QuoteReplyInterpretationLLM port ("Rex Response").

StubQuoteReplyInterpretationLLM reuses the original deterministic keyword
matcher as a no-credentials fallback (see application/quote_response_workflow
.interpret_quote_reply). OpenAIQuoteReplyInterpretationLLM is the real thing,
and can also pick up a revised price mentioned in the reply text.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from qinora.application.quote_response_workflow import interpret_quote_reply
from qinora.application.read_models import QuoteReplyIntent, QuoteReplyInterpretation
from qinora.infrastructure.llm.openai_client import OpenAIStructuredClient, require_openai_api_key
from qinora.infrastructure.settings import Settings

SYSTEM_PROMPT = """You are Rex Response, an assistant that reads a customer's free-text \
reply to a freight quote for the Qinora logistics platform and classifies their intent.

Rules:
- intent must be exactly one of: accepted, revise, rejected, unknown.
  - accepted: the customer clearly agrees to proceed with the quote as-is.
  - revise: the customer wants a different price or terms, but hasn't rejected outright.
  - rejected: the customer clearly declines the quote.
  - unknown: the reply's intent is unclear or unrelated to accepting/rejecting a quote.
- revised_price: if the customer proposes or mentions a specific new price, extract it \
as a plain number with no currency symbol. Otherwise null. Only set this when intent is \
"revise".
- confidence must reflect how clearly the text expresses one of the four intents: 1.0 \
for an unambiguous reply, lower if you had to infer, and low (<0.5) if it's genuinely \
unclear.
"""


class _QuoteReplySchema(BaseModel):
    intent: str = Field(description="One of: accepted, revise, rejected, unknown")
    revised_price: float | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class StubQuoteReplyInterpretationLLM:
    async def interpret(self, *, body_text: str) -> QuoteReplyInterpretation:
        intent = interpret_quote_reply(body_text)
        return QuoteReplyInterpretation(
            intent=intent,
            revised_price=None,
            confidence=1.0 if intent.value != "unknown" else 0.0,
        )


class OpenAIQuoteReplyInterpretationLLM:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def interpret(self, *, body_text: str) -> QuoteReplyInterpretation:
        client = OpenAIStructuredClient(
            require_openai_api_key(self._settings), self._settings.openai_model
        )
        result = await client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_text=body_text,
            schema=_QuoteReplySchema,
        )
        return QuoteReplyInterpretation(
            intent=QuoteReplyIntent(result.intent),
            revised_price=result.revised_price,
            confidence=result.confidence,
        )
