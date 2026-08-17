from dataclasses import dataclass

from qinora.application.operational_queries import CarrierIntelligenceCommand, OperationalQueries
from qinora.application.ports import (
    CarrierRfqRepository,
    EmailThreadRepository,
    OutboundReplyRepository,
    QuoteWriteRepository,
    ShipmentWriteRepository,
)
from qinora.application.read_models import QuoteRecord, ShipmentRecord

BOOKED_STATUS = "booked"


@dataclass(frozen=True)
class BookQuoteCommand:
    quote_id: str
    mode: str
    total_weight_kg: float
    requested_carrier_name: str | None = None
    min_confidence: float = 0.65
    # Who to notify with the shipment ID once booked - known by the caller
    # when acceptance came from an inbound email (the sender), left unset
    # for callers (e.g. the manual /quotes/{id}/reply endpoint) that don't
    # have a recipient on hand. No recipient just means no confirmation
    # email gets queued, booking itself is unaffected.
    recipient_email: str | None = None


@dataclass(frozen=True)
class BookingResult:
    shipment: ShipmentRecord
    selected_carrier_id: str | None
    requires_manual_review: bool
    overall_confidence: float


class BookingWorkflow:
    def __init__(
        self,
        quote_repository: QuoteWriteRepository,
        shipment_repository: ShipmentWriteRepository,
        operational_queries: OperationalQueries,
        carrier_rfqs: CarrierRfqRepository,
        outbound_repository: OutboundReplyRepository,
        email_threads: EmailThreadRepository | None = None,
    ) -> None:
        self._quote_repository = quote_repository
        self._shipment_repository = shipment_repository
        self._operational_queries = operational_queries
        self._carrier_rfqs = carrier_rfqs
        self._outbound_repository = outbound_repository
        self._email_threads = email_threads

    async def book_quote(self, command: BookQuoteCommand) -> BookingResult:
        quote = await self._quote_repository.mark_quote_accepted(command.quote_id)
        lane = await self._resolve_quote_lane(quote.request_id)

        # If this quote was priced from a carrier RFQ batch
        # (application/carrier_rfq_collector.py), book the exact carrier
        # that actually quoted it instead of re-running evaluate_carriers()
        # from scratch, which knows nothing about that history and could
        # easily rank a different (or no) carrier as "the" match.
        winning_rfq = (
            await self._carrier_rfqs.find_winning(quote.request_id) if quote.request_id else None
        )

        if winning_rfq is not None:
            selected_carrier_id: str | None = winning_rfq.carrier_id
            requires_manual_review = False
            overall_confidence = 1.0
        else:
            intelligence = await self._operational_queries.run_carrier_intelligence(
                CarrierIntelligenceCommand(
                    mode=command.mode,
                    total_weight_kg=command.total_weight_kg,
                    requested_carrier_name=command.requested_carrier_name,
                    min_confidence=command.min_confidence,
                )
            )
            selected_carrier_id = intelligence.selected_carrier_id
            requires_manual_review = intelligence.requires_manual_review
            overall_confidence = intelligence.overall_confidence

        status = "needs_review" if requires_manual_review else BOOKED_STATUS
        shipment = await self._shipment_repository.create_shipment(
            quote_id=quote.id,
            carrier_id=selected_carrier_id,
            lane=lane,
            status=status,
            eta="Väntar",
        )

        if status == BOOKED_STATUS and command.recipient_email:
            await self._outbound_repository.enqueue_quote(
                quote_id=quote.id,
                recipient=command.recipient_email,
                subject=f"Din bokning är bekräftad - {shipment.public_id}",
                body_text=(
                    f"Din frakt är bokad. Frakt-ID: {shipment.public_id}.\n\n"
                    "Vi återkommer med spårningsuppdateringar löpande.\n\n"
                    "Med vänlig hälsning,\nSandahls"
                ),
                in_reply_to_message_id=await self._latest_thread_message_id(quote),
            )

        return BookingResult(
            shipment=shipment,
            selected_carrier_id=selected_carrier_id,
            requires_manual_review=requires_manual_review,
            overall_confidence=overall_confidence,
        )

    async def _latest_thread_message_id(self, quote: QuoteRecord) -> str | None:
        if self._email_threads is None:
            return None
        history = await self._email_threads.list_thread_history(
            request_id=quote.request_id, quote_id=quote.id
        )
        return history[-1].message_id if history else None

    async def _resolve_quote_lane(self, request_id: str | None) -> str:
        if request_id is None:
            return "Väntar på sträckbekräftelse"

        requests = await self._operational_queries.list_requests()
        for request in requests:
            if request.id == request_id:
                return request.lane

        return "Väntar på sträckbekräftelse"
