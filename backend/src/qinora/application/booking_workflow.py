from dataclasses import dataclass

from qinora.application.greeting import greeting
from qinora.application.operational_queries import CarrierIntelligenceCommand, OperationalQueries
from qinora.application.ports import (
    CarrierRfqOutboundRepository,
    CarrierRfqRepository,
    EmailThreadRepository,
    OutboundReplyRepository,
    QuoteWriteRepository,
    ShipmentWriteRepository,
)
from qinora.application.quote_workflow import latest_customer_email
from qinora.application.read_models import InboundEmailRecord, QuoteRecord, ShipmentRecord

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
    # The request this quote belongs to, when the caller already knows it
    # reliably (e.g. application/email_intake_orchestrator.py's own
    # thread_matching result). Preferred over quote.request_id when given -
    # reproduced live 2026-09-17: a quote's own request_id ended up unset,
    # which silently broke picking the carrier that actually won the RFQ
    # (winning_rfq lookup below needs a real request_id) and skipped the
    # booking confirmation entirely (status fell back to "needs_review").
    request_id: str | None = None


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
        customer_mailbox: str | None = None,
        carrier_rfq_outbound: CarrierRfqOutboundRepository | None = None,
        carrier_mailbox: str | None = None,
    ) -> None:
        self._quote_repository = quote_repository
        self._shipment_repository = shipment_repository
        self._operational_queries = operational_queries
        self._carrier_rfqs = carrier_rfqs
        self._outbound_repository = outbound_repository
        self._email_threads = email_threads
        self._customer_mailbox = customer_mailbox
        # Used only to tell the winning carrier a booking is confirmed and
        # they should proceed with pickup, below - None (the default)
        # skips that notification, matching deployments that never set up
        # the second mailbox in the first place.
        self._carrier_rfq_outbound = carrier_rfq_outbound
        self._carrier_mailbox = carrier_mailbox

    async def book_quote(self, command: BookQuoteCommand) -> BookingResult:
        quote = await self._quote_repository.mark_quote_accepted(command.quote_id)
        request_id = command.request_id or quote.request_id
        lane = await self._resolve_quote_lane(request_id)

        # If this quote was priced from a carrier RFQ batch
        # (application/carrier_rfq_collector.py), book the exact carrier
        # that actually quoted it instead of re-running evaluate_carriers()
        # from scratch, which knows nothing about that history and could
        # easily rank a different (or no) carrier as "the" match.
        winning_rfq = await self._carrier_rfqs.find_winning(request_id) if request_id else None

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
            latest_message = await self._latest_thread_email(quote)
            greeting_line = greeting(
                latest_message.sender_name if latest_message else None,
                latest_message.sender if latest_message else command.recipient_email,
            )
            await self._outbound_repository.enqueue_quote(
                quote_id=quote.id,
                recipient=command.recipient_email,
                subject=f"Din bokning är bekräftad - {shipment.public_id}",
                body_text=_format_booking_confirmation(
                    quote, command, lane, shipment, greeting_line
                ),
                in_reply_to_message_id=latest_message.message_id if latest_message else None,
                sender_mailbox=self._customer_mailbox,
            )

        if status == BOOKED_STATUS and winning_rfq is not None and self._carrier_rfq_outbound:
            await self._notify_winning_carrier(winning_rfq.id, selected_carrier_id, shipment, lane)

        return BookingResult(
            shipment=shipment,
            selected_carrier_id=selected_carrier_id,
            requires_manual_review=requires_manual_review,
            overall_confidence=overall_confidence,
        )

    async def _notify_winning_carrier(
        self,
        carrier_rfq_id: str,
        carrier_id: str | None,
        shipment: ShipmentRecord,
        lane: str,
    ) -> None:
        """Tells the carrier whose RFQ reply won that the customer has
        booked - so they know to actually proceed with the pickup, not
        just that their price was noted. Every other step in this pipeline
        (customer quote, customer booking confirmation) is already a real
        email; the carrier was the one leg still silent. Best-effort: no
        carrier record, no email on file, or the outbound queue not wired
        up all just skip this rather than fail the booking itself.
        """
        if carrier_id is None:
            return
        carriers = await self._operational_queries.list_carriers()
        carrier = next((item for item in carriers if item.id == carrier_id), None)
        if carrier is None or not carrier.email:
            return

        assert self._carrier_rfq_outbound is not None
        subject = f"Bokning bekräftad - {shipment.public_id}"
        body_text = (
            f"Hej,\n\nKunden har bekräftat bokningen för {lane}.\n\n"
            f"Frakt-ID: {shipment.public_id}\n\n"
            "Vänligen boka in upphämtning enligt tidigare överenskommen offert.\n\n"
            "Med vänlig hälsning,\nSandahls"
        )
        await self._carrier_rfq_outbound.enqueue(
            carrier_rfq_id=carrier_rfq_id,
            recipient=carrier.email,
            subject=subject,
            body_text=body_text,
            sender_mailbox=self._carrier_mailbox,
        )

    async def _latest_thread_email(self, quote: QuoteRecord) -> InboundEmailRecord | None:
        if self._email_threads is None:
            return None
        history = await self._email_threads.list_thread_history(
            request_id=quote.request_id, quote_id=quote.id
        )
        return latest_customer_email(history)

    async def _resolve_quote_lane(self, request_id: str | None) -> str:
        if request_id is None:
            return "Väntar på sträckbekräftelse"

        requests = await self._operational_queries.list_requests()
        for request in requests:
            if request.id == request_id:
                return request.lane

        return "Väntar på sträckbekräftelse"


def _format_booking_confirmation(
    quote: QuoteRecord,
    command: BookQuoteCommand,
    lane: str,
    shipment: ShipmentRecord,
    greeting_line: str,
) -> str:
    # Matches the Route/Mode/Weight/Price recap + tracking-notice convention
    # already established in this mailbox's booking-confirmation history,
    # rather than inventing a new, less complete format from scratch.
    # Greets by first name (application/greeting.py) so it reads as a human
    # reply, not a form letter.
    return (
        f"{greeting_line}\n\n"
        "Tack för din bekräftelse! Din frakt är nu bokad.\n\n"
        f"Rutt: {lane}\n"
        f"Transportläge: {command.mode.upper()}\n"
        f"Vikt: {command.total_weight_kg:g} kg\n"
        f"Pris: {quote.customer_price:.2f} {quote.currency}\n"
        f"Frakt-ID: {shipment.public_id}\n\n"
        "Vi skickar spårningsinformation när frakten hämtas.\n\n"
        "Med vänlig hälsning,\nSandahls"
    )
