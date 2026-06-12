from dataclasses import dataclass

from qinora.application.ports import OperationalReadRepository
from qinora.application.read_models import (
    AgentLogRecord,
    CarrierRecord,
    ContactRecord,
    InboxRecord,
    InvoiceRecord,
    OperationalTaskRecord,
    OutboundReplyRecord,
    QuoteDetailRecord,
    QuoteRecord,
    RequestRecord,
    SearchResultRecord,
    ShipmentEventRecord,
    ShipmentRecord,
)
from qinora.domain import CarrierCandidate, CarrierEvaluationInput, TransportMode, evaluate_carriers


@dataclass(frozen=True)
class DashboardSummary:
    kpis: list[dict[str, str]]
    pipeline: list[dict[str, int | str]]
    agent_activity: list[dict[str, float | str]]


@dataclass(frozen=True)
class CarrierIntelligenceCommand:
    mode: str
    total_weight_kg: float
    requested_carrier_name: str | None
    min_confidence: float


class OperationalQueries:
    def __init__(self, repository: OperationalReadRepository) -> None:
        self._repository = repository

    async def dashboard_summary(self) -> DashboardSummary:
        requests = await self._repository.list_requests()
        agent_logs = await self._repository.list_agent_logs()
        tasks = await self._repository.list_operational_tasks()
        exceptions = len([item for item in tasks if item.status == "open"])
        open_requests = len([item for item in requests if item.status != "converted"])

        return DashboardSummary(
            kpis=[
                {"label": "Open requests", "value": str(open_requests), "trend": "+12%"},
                {"label": "On-time", "value": "96%", "trend": "+3%"},
                {"label": "Exceptions", "value": str(exceptions), "trend": "-18%"},
                {"label": "Agent health", "value": "98%", "trend": "+1%"},
            ],
            pipeline=[
                {"status": "New", "count": 8},
                {"status": "Parsing", "count": 3},
                {"status": "Quoted", "count": 12},
                {"status": "Booked", "count": 9},
                {"status": "In transit", "count": 17},
                {"status": "Needs review", "count": exceptions},
            ],
            agent_activity=[
                {
                    "agent": log.agent_name,
                    "event": log.step,
                    "confidence": log.confidence,
                }
                for log in agent_logs
            ],
        )

    async def list_requests(self) -> list[RequestRecord]:
        return await self._repository.list_requests()

    async def list_quotes(self) -> list[QuoteRecord]:
        return await self._repository.list_quotes()

    async def get_quote_detail(self, quote_id: str) -> QuoteDetailRecord | None:
        return await self._repository.get_quote_detail(quote_id)

    async def list_shipments(self) -> list[ShipmentRecord]:
        return await self._repository.list_shipments()

    async def list_invoices(self) -> list[InvoiceRecord]:
        return await self._repository.list_invoices()

    async def list_carriers(self) -> list[CarrierRecord]:
        return await self._repository.list_carriers()

    async def list_contacts(self) -> list[ContactRecord]:
        return await self._repository.list_contacts()

    async def list_inbox(self) -> list[InboxRecord]:
        return await self._repository.list_inbox()

    async def list_agent_logs(self) -> list[AgentLogRecord]:
        return await self._repository.list_agent_logs()

    async def list_operational_tasks(self) -> list[OperationalTaskRecord]:
        return await self._repository.list_operational_tasks()

    async def list_shipment_events(self, shipment_id: str) -> list[ShipmentEventRecord]:
        return await self._repository.list_shipment_events(shipment_id)

    async def list_outbound_replies(self) -> list[OutboundReplyRecord]:
        return await self._repository.list_outbound_replies()

    async def global_search(self, query: str, limit: int = 10) -> list[SearchResultRecord]:
        needle = query.strip().lower()
        if not needle:
            return []

        result_groups = await self._searchable_result_groups()
        scored_results = [
            (_score_result(result, needle), result)
            for results in result_groups
            for result in results
            if _score_result(result, needle) > 0
        ]
        scored_results.sort(key=lambda item: (-item[0], item[1].entity_type, item[1].public_id))
        return [result for _, result in scored_results[:limit]]

    async def _searchable_result_groups(self) -> list[list[SearchResultRecord]]:
        requests = await self._repository.list_requests()
        quotes = await self._repository.list_quotes()
        shipments = await self._repository.list_shipments()
        invoices = await self._repository.list_invoices()
        carriers = await self._repository.list_carriers()
        contacts = await self._repository.list_contacts()

        return [
            [
                SearchResultRecord(
                    id=request.id,
                    public_id=request.public_id,
                    entity_type="request",
                    label=f"{request.customer} transport request",
                    description=f"{request.lane} - {request.mode} - {request.status}",
                    href=f"/requests?highlight={request.id}",
                )
                for request in requests
            ],
            [
                SearchResultRecord(
                    id=quote.id,
                    public_id=quote.id,
                    entity_type="quote",
                    label=f"Quote {quote.id}",
                    description=f"{quote.status} - {quote.customer_price:g} {quote.currency}",
                    href=f"/quotes?highlight={quote.id}",
                )
                for quote in quotes
            ],
            [
                SearchResultRecord(
                    id=shipment.id,
                    public_id=shipment.public_id,
                    entity_type="shipment",
                    label=f"Shipment {shipment.public_id}",
                    description=f"{shipment.lane} - {shipment.status}",
                    href=f"/shipments?highlight={shipment.id}",
                )
                for shipment in shipments
            ],
            [
                SearchResultRecord(
                    id=invoice.id,
                    public_id=invoice.public_id,
                    entity_type="invoice",
                    label=f"Invoice {invoice.public_id}",
                    description=f"{invoice.status} - {invoice.invoice_amount:g} {invoice.currency}",
                    href=f"/invoices?highlight={invoice.id}",
                )
                for invoice in invoices
            ],
            [
                SearchResultRecord(
                    id=carrier.id,
                    public_id=carrier.id,
                    entity_type="carrier",
                    label=carrier.display_name,
                    description=f"{', '.join(carrier.modes)} - lane score {carrier.lane_score:g}",
                    href=f"/carriers?highlight={carrier.id}",
                )
                for carrier in carriers
            ],
            [
                SearchResultRecord(
                    id=contact.id,
                    public_id=contact.public_id,
                    entity_type="contact",
                    label=contact.display_name,
                    description=" - ".join(
                        part
                        for part in (contact.email, contact.domain, contact.payment_terms)
                        if part
                    ),
                    href=f"/contacts?highlight={contact.id}",
                )
                for contact in contacts
            ],
        ]

    async def run_carrier_intelligence(self, command: CarrierIntelligenceCommand):
        carriers = await self._repository.list_carriers()
        candidates = tuple(_to_candidate(carrier) for carrier in carriers)

        return evaluate_carriers(
            CarrierEvaluationInput(
                mode=TransportMode(command.mode),
                total_weight_kg=command.total_weight_kg,
                requested_carrier_name=command.requested_carrier_name,
                min_confidence=command.min_confidence,
                candidates=candidates,
            )
        )


def _to_candidate(carrier: CarrierRecord) -> CarrierCandidate:
    return CarrierCandidate(
        id=carrier.id,
        display_name=carrier.display_name,
        aliases=carrier.aliases,
        modes=tuple(TransportMode(mode) for mode in carrier.modes),
        lane_score=carrier.lane_score,
        max_weight_kg=carrier.max_weight_kg,
        performance_score=carrier.performance_score,
        preferred=carrier.preferred,
        sample_size=carrier.sample_size,
    )


def _score_result(result: SearchResultRecord, needle: str) -> int:
    fields = (
        result.public_id.lower(),
        result.id.lower(),
        result.label.lower(),
        result.description.lower(),
        result.entity_type.lower(),
    )
    if fields[0] == needle or fields[1] == needle:
        return 100
    if fields[0].startswith(needle) or fields[1].startswith(needle):
        return 80
    if any(field.startswith(needle) for field in fields[2:]):
        return 60
    if any(needle in field for field in fields):
        return 35
    return 0
