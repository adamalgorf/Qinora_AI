from dataclasses import dataclass
from datetime import datetime

from qinora.application.ports import OperationalReadRepository
from qinora.application.read_models import (
    AgentConfigRecord,
    AgentLogRecord,
    CarrierRecord,
    CaseNoteRecord,
    ContactDetailRecord,
    ContactRecord,
    DocumentRecord,
    InboxDetailRecord,
    InboxRecord,
    InvoiceRecord,
    OperationalTaskRecord,
    OutboundReplyRecord,
    QuoteDetailRecord,
    QuoteRecord,
    RequestDetailRecord,
    RequestRecord,
    SearchResultRecord,
    ShipmentEventRecord,
    ShipmentRecord,
)
from qinora.domain import (
    CarrierCandidate,
    CarrierEvaluationInput,
    TransportMode,
    evaluate_carriers,
    parse_transport_modes,
)

# Shipment statuses that mean "a human needs to look at this" (see the
# shipments.status check constraint in migrations/0001_initial.sql). Used to
# derive CaseRecord.status - there's no separate requires_manual_review flag
# surfaced on ShipmentRecord today, and the task spec asks not to add new
# repository methods purely for the Cases composition, so this reuses the
# status value that's already there.
_SHIPMENT_REVIEW_STATUSES = frozenset({"needs_review", "manual_review"})

_WEEKDAY_LABELS: dict[int, str] = {
    1: "Mån",
    2: "Tis",
    3: "Ons",
    4: "Tor",
    5: "Fre",
    6: "Lör",
    7: "Sön",
}

# Swedish defaults for automations whose agent_configs.config JSON doesn't
# carry an explicit "trigger" - inferred from each agent's actual purpose
# (see application/agent_config.py's DEFAULT_AGENT_CONFIGS and the modules
# named there: request_parsing_agent.py, carrier_offer_agent.py,
# quote_response_workflow.py).
_AUTOMATION_TRIGGER_DEFAULTS: dict[str, str] = {
    "request_parsing_agent": "Nytt inkommande RFQ-mejl",
    "carrier_offer_agent": "Transportörens svar på fraktförfrågan",
    "quote_response_agent": "Kundens svar på offert",
}


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


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


@dataclass(frozen=True)
class CaseRecord:
    id: str
    public_id: str
    customer: str
    category: str
    lane: str
    priority: str
    sla_due_at: str | None
    assignee: str | None
    status: str


@dataclass(frozen=True)
class CaseDetailRecord:
    case: CaseRecord
    request_detail: RequestDetailRecord
    quotes: tuple[QuoteRecord, ...]
    shipment: ShipmentRecord | None
    invoice: InvoiceRecord | None
    documents: tuple[DocumentRecord, ...]
    contact: ContactRecord | None
    notes: tuple[CaseNoteRecord, ...]
    activity: tuple[dict, ...]


@dataclass(frozen=True)
class AutomationRecord:
    agent_key: str
    agent_name: str
    trigger: str
    scope: str
    success_rate: float
    volume: int
    status: str


@dataclass(frozen=True)
class AnalyticsSummary:
    kpis: list[dict[str, str]]
    workload_by_weekday: list[dict[str, int | str]]
    top_exception_categories: list[dict[str, float | str | None]]


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
                {"label": "Öppna förfrågningar", "value": str(open_requests), "trend": "+12%"},
                {"label": "I tid", "value": "96%", "trend": "+3%"},
                {"label": "Avvikelser", "value": str(exceptions), "trend": "-18%"},
                {"label": "Agenthälsa", "value": "98%", "trend": "+1%"},
            ],
            pipeline=[
                {"status": "Nya", "count": 8},
                {"status": "Tolkas", "count": 3},
                {"status": "Offererad", "count": 12},
                {"status": "Bokad", "count": 9},
                {"status": "Under transport", "count": 17},
                {"status": "Behöver granskning", "count": exceptions},
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

    async def get_request_detail(self, request_id: str) -> RequestDetailRecord | None:
        return await self._repository.get_request_detail(request_id)

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

    async def get_inbox_detail(self, message_id: str) -> InboxDetailRecord | None:
        return await self._repository.get_inbox_detail(message_id)

    async def list_agent_logs(self) -> list[AgentLogRecord]:
        return await self._repository.list_agent_logs()

    async def list_operational_tasks(self) -> list[OperationalTaskRecord]:
        return await self._repository.list_operational_tasks()

    async def list_shipment_events(self, shipment_id: str) -> list[ShipmentEventRecord]:
        return await self._repository.list_shipment_events(shipment_id)

    async def list_outbound_replies(self) -> list[OutboundReplyRecord]:
        return await self._repository.list_outbound_replies()

    async def list_documents(self) -> list[DocumentRecord]:
        return await self._repository.list_documents()

    async def get_contact_detail(self, contact_id: str) -> ContactDetailRecord | None:
        return await self._repository.get_contact_detail(contact_id)

    async def list_case_notes(self, request_id: str) -> list[CaseNoteRecord]:
        return await self._repository.list_case_notes(request_id)

    async def list_cases(self) -> list[CaseRecord]:
        requests = await self._repository.list_requests()
        quotes = await self._repository.list_quotes()
        shipments = await self._repository.list_shipments()

        shipments_by_quote = {
            shipment.quote_id: shipment for shipment in shipments if shipment.quote_id
        }
        quotes_by_request: dict[str, list[QuoteRecord]] = {}
        for quote in quotes:
            if quote.request_id:
                quotes_by_request.setdefault(quote.request_id, []).append(quote)

        cases = []
        for request in requests:
            shipment = _find_shipment_for_request(request.id, quotes_by_request, shipments_by_quote)
            cases.append(
                CaseRecord(
                    id=request.id,
                    public_id=request.public_id,
                    customer=request.customer,
                    category=request.mode,
                    lane=request.lane,
                    priority=request.priority,
                    sla_due_at=request.sla_due_at,
                    assignee=request.assignee,
                    status=_case_status(request.status, shipment),
                )
            )
        return cases

    async def get_case_detail(self, request_id: str) -> CaseDetailRecord | None:
        request_detail = await self._repository.get_request_detail(request_id)
        if request_detail is None:
            return None

        quotes_all = await self._repository.list_quotes()
        case_quotes = tuple(quote for quote in quotes_all if quote.request_id == request_id)
        quote_ids = {quote.id for quote in case_quotes}

        shipments_all = await self._repository.list_shipments()
        shipment = next((s for s in shipments_all if s.quote_id in quote_ids), None)

        invoice = None
        if shipment is not None:
            invoices_all = await self._repository.list_invoices()
            invoice = next((inv for inv in invoices_all if inv.shipment_id == shipment.id), None)

        documents_all = await self._repository.list_documents()
        documents = tuple(doc for doc in documents_all if doc.request_id == request_id)

        contacts_all = await self._repository.list_contacts()
        # Best-effort match: no adapter in this codebase populates a
        # contact_id FK on transport_requests, so we match on customer name
        # (see ContactDetailRecord's docstring for the same fallback).
        contact = next(
            (c for c in contacts_all if c.display_name == request_detail.request.customer),
            None,
        )

        notes = tuple(await self._repository.list_case_notes(request_id))

        agent_logs_all = await self._repository.list_agent_logs()
        relevant_entity_ids = {request_detail.request.id, request_detail.request.public_id}
        relevant_entity_ids.update(quote_ids)
        if shipment is not None:
            relevant_entity_ids.add(shipment.id)
            relevant_entity_ids.add(shipment.public_id)

        activity: list[dict] = [
            {
                "type": "agent_log",
                "timestamp": log.created_at,
                "tag": log.agent_name,
                "description": log.step,
            }
            for log in agent_logs_all
            if log.entity_id in relevant_entity_ids
        ]

        if shipment is not None:
            for event in await self._repository.list_shipment_events(shipment.id):
                activity.append(
                    {
                        "type": "shipment_event",
                        "timestamp": event.created_at,
                        "tag": event.to_status,
                        "description": event.reason
                        or f"{event.from_status or '—'} → {event.to_status}",
                    }
                )

        for note in notes:
            activity.append(
                {
                    "type": "case_note",
                    "timestamp": note.created_at,
                    "tag": note.author,
                    "description": note.body_text,
                }
            )

        activity.sort(key=lambda item: item["timestamp"] or "")

        return CaseDetailRecord(
            case=CaseRecord(
                id=request_detail.request.id,
                public_id=request_detail.request.public_id,
                customer=request_detail.request.customer,
                category=request_detail.request.mode,
                lane=request_detail.request.lane,
                priority=request_detail.request.priority,
                sla_due_at=request_detail.request.sla_due_at,
                assignee=request_detail.request.assignee,
                status=_case_status(request_detail.request.status, shipment),
            ),
            request_detail=request_detail,
            quotes=case_quotes,
            shipment=shipment,
            invoice=invoice,
            documents=documents,
            contact=contact,
            notes=notes,
            activity=tuple(activity),
        )

    async def list_automations(
        self, agent_configs: list[AgentConfigRecord]
    ) -> list[AutomationRecord]:
        agent_logs = await self._repository.list_agent_logs()

        automations = []
        for config in agent_configs:
            logs_for_agent = [log for log in agent_logs if log.agent_key == config.agent_key]
            volume = len(logs_for_agent)
            # "Success" = the agent's own configured confidence gate was
            # cleared. agent_logs doesn't separately record whether a result
            # was auto-applied vs. routed to a human, so this is the closest
            # existing signal to a success rate (see
            # application/agent_config.py's should_auto_act, which gates on
            # the same confidence/min_confidence comparison).
            successful = len(
                [log for log in logs_for_agent if log.confidence >= config.min_confidence]
            )
            success_rate = successful / volume if volume else 0.0

            automations.append(
                AutomationRecord(
                    agent_key=config.agent_key,
                    agent_name=config.agent_name,
                    trigger=str(
                        config.config.get("trigger")
                        or _AUTOMATION_TRIGGER_DEFAULTS.get(config.agent_key, "—")
                    ),
                    scope=str(config.config.get("scope") or "—"),
                    success_rate=success_rate,
                    volume=volume,
                    status="active" if config.is_enabled else "paused",
                )
            )
        return automations

    async def analytics_summary(self) -> AnalyticsSummary:
        agent_logs = await self._repository.list_agent_logs()
        tasks = await self._repository.list_operational_tasks()
        requests = await self._repository.list_requests()

        converted = len([item for item in requests if item.status == "converted"])
        conversion_rate = (converted / len(requests) * 100) if requests else 0.0
        # No task in this codebase is ever moved out of "open" today (see
        # application/*.py's create_task() call sites) - "closed" is the
        # forward-looking state a resolution flow would set, so these two
        # metrics report real zeros until that flow ships rather than
        # fabricating activity.
        closed_tasks = [task for task in tasks if task.status == "closed"]

        kpis = [
            {
                "label": "Sparade operatörstimmar",
                # Rough estimate, not measured time: ~6 minutes saved per
                # automated agent action, no operator time-tracking data
                # exists yet to compute this for real.
                "value": f"{len(agent_logs) * 6 / 60:.0f} h",
                "trend": "+8%",
            },
            {
                "label": "Konverteringsgrad",
                "value": f"{conversion_rate:.0f}%",
                "trend": "+4%",
            },
            {
                # Static placeholder, same spirit as dashboard_summary()'s
                # "I tid"/"Agenthälsa" entries above - no per-message
                # response-time instrumentation exists yet to compute this.
                "label": "AI-svarstid",
                "value": "< 2 min",
                "trend": "+5%",
            },
            {
                "label": "Hanterade avvikelser",
                "value": str(len(closed_tasks)),
                "trend": "+0%",
            },
        ]

        ai_counts: dict[int, int] = {}
        for log in agent_logs:
            parsed = _parse_timestamp(log.created_at)
            if parsed is not None:
                ai_counts[parsed.isoweekday()] = ai_counts.get(parsed.isoweekday(), 0) + 1

        manual_counts: dict[int, int] = {}
        # Explicitly-approved best-effort proxy, not exact operator-time
        # tracking: closed operational_tasks grouped by the weekday they
        # were created on.
        for task in closed_tasks:
            parsed = _parse_timestamp(task.created_at)
            if parsed is not None:
                manual_counts[parsed.isoweekday()] = manual_counts.get(parsed.isoweekday(), 0) + 1

        workload_by_weekday = [
            {
                "weekday": _WEEKDAY_LABELS[day],
                "ai": ai_counts.get(day, 0),
                "manual": manual_counts.get(day, 0),
            }
            for day in range(1, 8)
        ]

        requests_by_id = {request.id: request for request in requests}
        reason_groups: dict[str, list[OperationalTaskRecord]] = {}
        for task in tasks:
            reason_groups.setdefault(task.reason, []).append(task)
        total_tasks = len(tasks)
        ranked_reasons = sorted(
            reason_groups.items(), key=lambda item: len(item[1]), reverse=True
        )

        top_exception_categories = []
        for reason, group in ranked_reasons[:5]:
            location = None
            for task in group:
                # "transport_request" is the actual entity_type string this
                # codebase writes (see e.g. application/pricing_engine.py,
                # application/request_intake.py) - the task brief called it
                # "request".
                if task.entity_type == "transport_request":
                    request = requests_by_id.get(task.entity_id)
                    if request is not None:
                        location = request.lane
                        break
            top_exception_categories.append(
                {
                    "category": reason,
                    "percent": round(len(group) / total_tasks * 100, 1) if total_tasks else 0.0,
                    "location": location,
                }
            )

        return AnalyticsSummary(
            kpis=kpis,
            workload_by_weekday=workload_by_weekday,
            top_exception_categories=top_exception_categories,
        )

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

        # Cases replace the old /requests, /shipments and /invoices detail
        # pages, so search results for all three now deep-link into a case.
        # Shipments/invoices don't carry a request id directly - resolve one
        # through their quote when possible, otherwise fall back to a
        # highlight-only /cases link rather than a broken /shipments link.
        quotes_by_id = {quote.id: quote for quote in quotes}

        def _case_href(request_id: str | None, fallback_id: str) -> str:
            if request_id:
                return f"/cases/{request_id}"
            return f"/cases?highlight={fallback_id}"

        return [
            [
                SearchResultRecord(
                    id=request.id,
                    public_id=request.public_id,
                    entity_type="request",
                    label=f"{request.customer} transport request",
                    description=f"{request.lane} - {request.mode} - {request.status}",
                    href=f"/cases/{request.id}",
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
                    href=_case_href(
                        quotes_by_id[shipment.quote_id].request_id
                        if shipment.quote_id in quotes_by_id
                        else None,
                        shipment.id,
                    ),
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
                    href=_case_href(
                        quotes_by_id[invoice.quote_id].request_id
                        if invoice.quote_id in quotes_by_id
                        else None,
                        invoice.id,
                    ),
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


def _find_shipment_for_request(
    request_id: str,
    quotes_by_request: dict[str, list[QuoteRecord]],
    shipments_by_quote: dict[str, ShipmentRecord],
) -> ShipmentRecord | None:
    for quote in quotes_by_request.get(request_id, []):
        shipment = shipments_by_quote.get(quote.id)
        if shipment is not None:
            return shipment
    return None


def _case_status(request_status: str, shipment: ShipmentRecord | None) -> str:
    if shipment is not None and shipment.status in _SHIPMENT_REVIEW_STATUSES:
        return "requires_review"
    return request_status


def _to_candidate(carrier: CarrierRecord) -> CarrierCandidate:
    return CarrierCandidate(
        id=carrier.id,
        display_name=carrier.display_name,
        aliases=carrier.aliases,
        modes=parse_transport_modes(carrier.modes),
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
