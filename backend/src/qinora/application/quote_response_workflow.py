from dataclasses import dataclass
from enum import StrEnum

from qinora.application.booking_workflow import BookingResult, BookingWorkflow, BookQuoteCommand
from qinora.application.ports import QuoteResponseEventRepository, QuoteWriteRepository
from qinora.application.read_models import QuoteRecord, QuoteResponseEventRecord


class QuoteReplyIntent(StrEnum):
    ACCEPTED = "accepted"
    REVISE = "revise"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


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
    quote: QuoteRecord | None = None
    revised_quote: QuoteRecord | None = None
    booking: BookingResult | None = None


class QuoteResponseWorkflow:
    def __init__(
        self,
        quote_repository: QuoteWriteRepository,
        event_repository: QuoteResponseEventRepository,
        booking_workflow: BookingWorkflow,
    ) -> None:
        self._quote_repository = quote_repository
        self._event_repository = event_repository
        self._booking_workflow = booking_workflow

    async def interpret_reply(
        self,
        command: InterpretQuoteReplyCommand,
    ) -> InterpretQuoteReplyResult:
        intent = interpret_quote_reply(command.body_text)
        event = await self._event_repository.record_response(
            quote_id=command.quote_id,
            intent=intent.value,
            body_text=command.body_text,
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
                quote=quote,
                booking=booking,
            )

        if intent is QuoteReplyIntent.REJECTED:
            quote = await self._quote_repository.mark_quote_rejected(command.quote_id)
            return InterpretQuoteReplyResult(intent=intent, event=event, quote=quote)

        if intent is QuoteReplyIntent.REVISE:
            original = await self._quote_repository.mark_quote_revision_requested(command.quote_id)
            revised_quote = await self._quote_repository.create_revision(
                previous_quote_id=command.quote_id,
                customer_price=command.revised_customer_price or original.customer_price,
                currency=original.currency,
            )
            return InterpretQuoteReplyResult(
                intent=intent,
                event=event,
                quote=original,
                revised_quote=revised_quote,
            )

        quote = await self._quote_repository.get_quote_record(command.quote_id)
        return InterpretQuoteReplyResult(intent=intent, event=event, quote=quote)


def interpret_quote_reply(body_text: str) -> QuoteReplyIntent:
    normalized = body_text.casefold()
    accepted_keywords = ("accept", "accepted", "ok", "approved", "go ahead")
    revise_keywords = ("revise", "revision", "change", "lower price", "update")
    rejected_keywords = ("reject", "rejected", "decline", "no thanks")

    if any(keyword in normalized for keyword in accepted_keywords):
        return QuoteReplyIntent.ACCEPTED
    if any(keyword in normalized for keyword in revise_keywords):
        return QuoteReplyIntent.REVISE
    if any(keyword in normalized for keyword in rejected_keywords):
        return QuoteReplyIntent.REJECTED
    return QuoteReplyIntent.UNKNOWN
