from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from qinora.application.booking_workflow import BookingResult, BookingWorkflow, BookQuoteCommand
from qinora.application.invoice_audit import (
    CreateInvoiceAuditCommand,
    InvoiceAuditResult,
    InvoiceAuditWorkflow,
)
from qinora.application.outbound_mailer import (
    ProcessOutboundQueueCommand,
    ProcessOutboundQueueResult,
    ProcessOutboundQueueUseCase,
)
from qinora.application.quote_workflow import (
    CreateQuoteCommand,
    QuoteWorkflow,
    SendQuoteCommand,
    SendQuoteResult,
)
from qinora.application.read_models import QuoteRecord, RequestRecord, ShipmentRecord
from qinora.application.request_intake import (
    CargoLineCommand,
    CreateRequestCommand,
    CreateRequestResult,
    CreateRequestUseCase,
)
from qinora.application.shipment_workflow import ShipmentWorkflow, UpdateShipmentStatusCommand


@dataclass(frozen=True)
class DemoFlowResult:
    request: RequestRecord
    quote: SendQuoteResult
    final_quote: QuoteRecord
    outbound_queue: ProcessOutboundQueueResult
    booking: BookingResult
    final_shipment: ShipmentRecord
    invoice: InvoiceAuditResult
    steps: tuple[str, ...]


class DemoFlowUseCase:
    def __init__(
        self,
        create_request: CreateRequestUseCase,
        quote_workflow: QuoteWorkflow,
        outbound_queue: ProcessOutboundQueueUseCase,
        booking_workflow: BookingWorkflow,
        shipment_workflow: ShipmentWorkflow,
        invoice_audit: InvoiceAuditWorkflow,
    ) -> None:
        self._create_request = create_request
        self._quote_workflow = quote_workflow
        self._outbound_queue = outbound_queue
        self._booking_workflow = booking_workflow
        self._shipment_workflow = shipment_workflow
        self._invoice_audit = invoice_audit

    async def run(self) -> DemoFlowResult:
        request_result = await self._create_transport_request()
        quote = await self._quote_workflow.create_quote(
            CreateQuoteCommand(
                request_id=request_result.request.id,
                customer_price=12650,
                currency="SEK",
            )
        )
        sent_quote = await self._quote_workflow.send_quote(
            SendQuoteCommand(quote_id=quote.id, recipient="ops@demo-customer.example")
        )
        outbound_queue = await self._outbound_queue.execute(ProcessOutboundQueueCommand(limit=10))
        booking = await self._booking_workflow.book_quote(
            BookQuoteCommand(
                quote_id=sent_quote.quote.id,
                mode="ltl",
                total_weight_kg=820,
                requested_carrier_name="Nordic",
                min_confidence=0.65,
            )
        )
        await self._shipment_workflow.update_status(
            UpdateShipmentStatusCommand(
                shipment_id=booking.shipment.id,
                status="in_transit",
                reason="Demo flow picked up by carrier",
            )
        )
        await self._shipment_workflow.update_status(
            UpdateShipmentStatusCommand(
                shipment_id=booking.shipment.id,
                status="delivered",
                reason="Demo flow delivery confirmation",
            )
        )
        invoice = await self._invoice_audit.audit_invoice(
            CreateInvoiceAuditCommand(
                shipment_id=booking.shipment.id,
                invoice_amount=12650,
                max_discrepancy=250,
            )
        )
        final_shipment = replace(booking.shipment, status=invoice.shipment_status)
        final_quote = replace(sent_quote.quote, status="accepted")

        return DemoFlowResult(
            request=request_result.request,
            quote=sent_quote,
            final_quote=final_quote,
            outbound_queue=outbound_queue,
            booking=booking,
            final_shipment=final_shipment,
            invoice=invoice,
            steps=(
                "Transport request created",
                "Quote priced and sent",
                "Outbound email processed",
                "Quote accepted and shipment booked",
                "Shipment delivered",
                "Invoice audited and approved",
            ),
        )

    async def _create_transport_request(self) -> CreateRequestResult:
        return await self._create_request.execute(
            CreateRequestCommand(
                customer="QiNora Demo Customer",
                origin="Gothenburg",
                destination="Hamburg",
                mode="ltl",
                loading_time=datetime.now(UTC) + timedelta(days=1),
                cargo=(
                    CargoLineCommand(
                        description="Demo pallets",
                        quantity=2,
                        weight_kg=820,
                        length_cm=120,
                        width_cm=80,
                        height_cm=150,
                    ),
                ),
            )
        )
