from dataclasses import dataclass

from qinora.application.operational_queries import CarrierIntelligenceCommand, OperationalQueries
from qinora.application.ports import QuoteWriteRepository, ShipmentWriteRepository
from qinora.application.read_models import ShipmentRecord


@dataclass(frozen=True)
class BookQuoteCommand:
    quote_id: str
    mode: str
    total_weight_kg: float
    requested_carrier_name: str | None = None
    min_confidence: float = 0.65


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
    ) -> None:
        self._quote_repository = quote_repository
        self._shipment_repository = shipment_repository
        self._operational_queries = operational_queries

    async def book_quote(self, command: BookQuoteCommand) -> BookingResult:
        quote = await self._quote_repository.mark_quote_accepted(command.quote_id)
        lane = await self._resolve_quote_lane(quote.request_id)
        intelligence = await self._operational_queries.run_carrier_intelligence(
            CarrierIntelligenceCommand(
                mode=command.mode,
                total_weight_kg=command.total_weight_kg,
                requested_carrier_name=command.requested_carrier_name,
                min_confidence=command.min_confidence,
            )
        )
        status = "needs_review" if intelligence.requires_manual_review else "booked"
        shipment = await self._shipment_repository.create_shipment(
            quote_id=quote.id,
            carrier_id=intelligence.selected_carrier_id,
            lane=lane,
            status=status,
            eta="Väntar",
        )

        return BookingResult(
            shipment=shipment,
            selected_carrier_id=intelligence.selected_carrier_id,
            requires_manual_review=intelligence.requires_manual_review,
            overall_confidence=intelligence.overall_confidence,
        )

    async def _resolve_quote_lane(self, request_id: str | None) -> str:
        if request_id is None:
            return "Väntar på sträckbekräftelse"

        requests = await self._operational_queries.list_requests()
        for request in requests:
            if request.id == request_id:
                return request.lane

        return "Väntar på sträckbekräftelse"
