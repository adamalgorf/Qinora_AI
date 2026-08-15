from dataclasses import dataclass

from qinora.application.agent_config import AgentConfigService, should_auto_act
from qinora.application.booking_workflow import BookingResult, BookingWorkflow, BookQuoteCommand
from qinora.application.ports import (
    AgentLogWriteRepository,
    QuoteReplyInterpretationLLM,
    QuoteResponseEventRepository,
    QuoteWriteRepository,
)
from qinora.application.read_models import QuoteRecord, QuoteReplyIntent, QuoteResponseEventRecord

AGENT_KEY = "quote_response_agent"
AGENT_NAME = "Rex Response"


@dataclass(frozen=True)
class InterpretQuoteReplyCommand:
    quote_id: str
    body_text: str
    mode: str = "ltl"
    total_weight_kg: float = 820
    requested_carrier_name: str | None = "Nordic"
    min_confidence: float = 0.65
    revised_customer_price: float | None = None


@dataclass(frozen=True)
class InterpretQuoteReplyResult:
    intent: QuoteReplyIntent
    event: QuoteResponseEventRecord
    needs_human_review: bool
    quote: QuoteRecord | None = None
    revised_quote: QuoteRecord | None = None
    booking: BookingResult | None = None


class QuoteResponseWorkflow:
    def __init__(
        self,
        quote_repository: QuoteWriteRepository,
        event_repository: QuoteResponseEventRepository,
        booking_workflow: BookingWorkflow,
        interpretation_llm: QuoteReplyInterpretationLLM,
        agent_logs: AgentLogWriteRepository,
        agent_config: AgentConfigService,
    ) -> None:
        self._quote_repository = quote_repository
        self._event_repository = event_repository
        self._booking_workflow = booking_workflow
        self._interpretation_llm = interpretation_llm
        self._agent_logs = agent_logs
        self._agent_config = agent_config

    async def interpret_reply(
        self,
        command: InterpretQuoteReplyCommand,
    ) -> InterpretQuoteReplyResult:
        interpretation = await self._interpretation_llm.interpret(body_text=command.body_text)
        intent = interpretation.intent
        event = await self._event_repository.record_response(
            quote_id=command.quote_id,
            intent=intent.value,
            body_text=command.body_text,
        )

        config = await self._agent_config.get_config(AGENT_KEY)
        can_auto_act = should_auto_act(config, interpretation.confidence)
        needs_review = not can_auto_act or intent is QuoteReplyIntent.UNKNOWN

        await self._agent_logs.record(
            agent_key=AGENT_KEY,
            agent_name=AGENT_NAME,
            step=(
                f"Interpreted quote {command.quote_id} reply as {intent.value}"
                if not needs_review
                else f"Low-confidence reply for quote {command.quote_id}, flagged for review"
            ),
            entity_id=command.quote_id,
            confidence=interpretation.confidence,
        )

        if needs_review:
            quote = await self._quote_repository.get_quote_record(command.quote_id)
            return InterpretQuoteReplyResult(
                intent=intent,
                event=event,
                needs_human_review=True,
                quote=quote,
            )

        if intent is QuoteReplyIntent.ACCEPTED:
            booking = await self._booking_workflow.book_quote(
                BookQuoteCommand(
                    quote_id=command.quote_id,
                    mode=command.mode,
                    total_weight_kg=command.total_weight_kg,
                    requested_carrier_name=command.requested_carrier_name,
                    min_confidence=command.min_confidence,
                )
            )
            quote = await self._quote_repository.get_quote_record(command.quote_id)
            return InterpretQuoteReplyResult(
                intent=intent,
                event=event,
                needs_human_review=False,
                quote=quote,
                booking=booking,
            )

        if intent is QuoteReplyIntent.REJECTED:
            quote = await self._quote_repository.mark_quote_rejected(command.quote_id)
            return InterpretQuoteReplyResult(
                intent=intent, event=event, needs_human_review=False, quote=quote
            )

        # REVISE
        original = await self._quote_repository.mark_quote_revision_requested(command.quote_id)
        revised_quote = await self._quote_repository.create_revision(
            previous_quote_id=command.quote_id,
            customer_price=(
                interpretation.revised_price
                or command.revised_customer_price
                or original.customer_price
            ),
            currency=original.currency,
        )
        return InterpretQuoteReplyResult(
            intent=intent,
            event=event,
            needs_human_review=False,
            quote=original,
            revised_quote=revised_quote,
        )


def interpret_quote_reply(body_text: str) -> QuoteReplyIntent:
    """Deterministic keyword classifier - the stub QuoteReplyInterpretationLLM
    implementation (see infrastructure/llm/quote_reply_interpretation.py).
    """
    normalized = body_text.casefold()
    # QiNora's own quote email is Swedish (see QuoteWorkflow.send_quote) - the
    # keyword lists need both languages since replies come in whichever
    # language the customer writes back in.
    accepted_keywords = (
        "accept",
        "accepted",
        "ok",
        "approved",
        "go ahead",
        "godkänn",
        "godkänner",
        "godkänd",
        "ja tack",
        "tackar ja",
    )
    revise_keywords = (
        "revise",
        "revision",
        "change",
        "lower price",
        "update",
        "ändra",
        "revidera",
        "justera",
        "lägre pris",
    )
    rejected_keywords = (
        "reject",
        "rejected",
        "decline",
        "no thanks",
        "avböjer",
        "avböjs",
        "nej tack",
        "refuserar",
    )

    if any(keyword in normalized for keyword in accepted_keywords):
        return QuoteReplyIntent.ACCEPTED
    if any(keyword in normalized for keyword in revise_keywords):
        return QuoteReplyIntent.REVISE
    if any(keyword in normalized for keyword in rejected_keywords):
        return QuoteReplyIntent.REJECTED
    return QuoteReplyIntent.UNKNOWN
