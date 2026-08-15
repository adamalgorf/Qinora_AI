from typing import Protocol

from qinora.application.read_models import (
    AgentConfigRecord,
    AgentLogRecord,
    CarrierOfferRecord,
    CarrierRecord,
    ContactRecord,
    InboundEmailRecord,
    InboxDetailRecord,
    InboxRecord,
    InvoiceRecord,
    OperationalTaskRecord,
    OutboundReplyRecord,
    ParsedCarrierOfferDraft,
    ParsedTransportRequestDraft,
    QuoteDetailRecord,
    QuoteRecord,
    QuoteReplyInterpretation,
    QuoteResponseEventRecord,
    RateProfileRecord,
    RequestDetailRecord,
    RequestRecord,
    ShipmentEventRecord,
    ShipmentRecord,
    StaleRequestRecord,
)
from qinora.domain import Quote, TransportRequestInput


class WebhookEventRepository(Protocol):
    async def exists(self, idempotency_key: str) -> bool:
        pass

    async def record(self, idempotency_key: str, event_type: str) -> None:
        pass


class InboundEmailRepository(Protocol):
    async def save(
        self,
        *,
        idempotency_key: str,
        sender: str,
        subject: str,
        body_text: str,
        recipient: str = "",
        message_id: str | None = None,
        in_reply_to: str | None = None,
        references_header: str | None = None,
    ) -> str:
        pass


class EmailThreadRepository(Protocol):
    """Threading lookups over email_inbound, plus the write-back methods the
    intake orchestrator uses to record its gating decision and link a
    message to the request/quote it resolved to (see
    application/thread_matching.py and application/email_intake_orchestrator.py).
    """

    async def get(self, email_id: str) -> InboundEmailRecord | None:
        pass

    async def find_candidates_by_message_ids(
        self, message_ids: tuple[str, ...]
    ) -> list[InboundEmailRecord]:
        pass

    async def find_candidates_by_sender(
        self, sender: str, limit: int = 200
    ) -> list[InboundEmailRecord]:
        pass

    async def find_candidates_by_domain(
        self, domain: str, limit: int = 200
    ) -> list[InboundEmailRecord]:
        pass

    async def list_thread_history(
        self, *, request_id: str | None, quote_id: str | None
    ) -> list[InboundEmailRecord]:
        pass

    async def link_thread(
        self, email_id: str, *, request_id: str | None, quote_id: str | None
    ) -> None:
        pass

    async def mark_classification(self, email_id: str, classification: str) -> None:
        pass


class ContactReadRepository(Protocol):
    async def find_by_sender(self, sender: str) -> ContactRecord | None:
        pass


class AgentLogWriteRepository(Protocol):
    async def record(
        self,
        *,
        agent_key: str,
        agent_name: str,
        step: str,
        entity_id: str,
        confidence: float,
    ) -> AgentLogRecord:
        pass


class AgentConfigRepository(Protocol):
    async def list_configs(self) -> list[AgentConfigRecord]:
        pass

    async def update_config(
        self,
        *,
        agent_key: str,
        is_enabled: bool,
        auto_mode: str,
        min_confidence: float,
    ) -> AgentConfigRecord:
        pass


class AgentDispatcher(Protocol):
    async def dispatch(self, *, event_type: str, entity_id: str) -> None:
        pass


class RequestParsingLLM(Protocol):
    """Turns free text (e.g. an RFQ email body) into a structured draft
    transport request. The only thing application code knows about the
    "Parsek" agent - implementations live in infrastructure/llm/.
    """

    async def parse(self, *, raw_text: str) -> ParsedTransportRequestDraft:
        pass


class CarrierOfferParsingLLM(Protocol):
    """Turns free text (a carrier's reply to a booking request) into a
    structured draft offer - the "Remy Rates" agent's only LLM dependency.
    """

    async def parse(self, *, raw_text: str) -> ParsedCarrierOfferDraft:
        pass


class QuoteReplyInterpretationLLM(Protocol):
    """Turns a customer's free-text reply to a quote into a structured
    intent (accept/revise/reject) plus any revised price mentioned - the
    "Rex Response" agent's only LLM dependency.
    """

    async def interpret(self, *, body_text: str) -> QuoteReplyInterpretation:
        pass


class CarrierOfferWriteRepository(Protocol):
    async def create_offer(
        self,
        *,
        request_id: str,
        carrier_name: str,
        price: float | None,
        currency: str | None,
        transit_days: int | None,
        notes: str | None,
        confidence: float,
    ) -> CarrierOfferRecord:
        pass

    async def list_offers_for_request(self, request_id: str) -> list[CarrierOfferRecord]:
        pass


class OperationalReadRepository(Protocol):
    async def list_requests(self) -> list[RequestRecord]:
        pass

    async def get_request_detail(self, request_id: str) -> RequestDetailRecord | None:
        pass

    async def list_quotes(self) -> list[QuoteRecord]:
        pass

    async def get_quote_detail(self, quote_id: str) -> QuoteDetailRecord | None:
        pass

    async def list_shipments(self) -> list[ShipmentRecord]:
        pass

    async def list_invoices(self) -> list[InvoiceRecord]:
        pass

    async def list_carriers(self) -> list[CarrierRecord]:
        pass

    async def list_contacts(self) -> list[ContactRecord]:
        pass

    async def list_inbox(self) -> list[InboxRecord]:
        pass

    async def get_inbox_detail(self, message_id: str) -> InboxDetailRecord | None:
        pass

    async def list_agent_logs(self) -> list[AgentLogRecord]:
        pass

    async def list_operational_tasks(self) -> list[OperationalTaskRecord]:
        pass

    async def list_shipment_events(self, shipment_id: str) -> list[ShipmentEventRecord]:
        pass

    async def list_outbound_replies(self) -> list[OutboundReplyRecord]:
        pass


class RequestWriteRepository(Protocol):
    async def create_transport_request(
        self,
        *,
        customer: str,
        lane: str,
        request: TransportRequestInput,
        status: str,
        review_reason: str | None,
    ) -> RequestRecord:
        pass

    async def update_transport_request(
        self,
        *,
        request_id: str,
        customer: str,
        lane: str,
        request: TransportRequestInput,
        status: str,
        review_reason: str | None,
    ) -> RequestRecord:
        pass


class StaleRequestRepository(Protocol):
    async def list_stale_requests(self, cutoff: str) -> list[StaleRequestRecord]:
        pass


class QuoteWriteRepository(Protocol):
    async def create_quote(
        self,
        *,
        request_id: str,
        customer_price: float,
        currency: str,
    ) -> QuoteRecord:
        pass

    async def get_quote(self, quote_id: str) -> Quote | None:
        pass

    async def get_quote_record(self, quote_id: str) -> QuoteRecord | None:
        pass

    async def mark_quote_sent(self, quote_id: str) -> QuoteRecord:
        pass

    async def mark_quote_accepted(self, quote_id: str) -> QuoteRecord:
        pass

    async def mark_quote_rejected(self, quote_id: str) -> QuoteRecord:
        pass

    async def mark_quote_revision_requested(self, quote_id: str) -> QuoteRecord:
        pass

    async def create_revision(
        self,
        *,
        previous_quote_id: str,
        customer_price: float,
        currency: str,
    ) -> QuoteRecord:
        pass


class QuoteResponseEventRepository(Protocol):
    async def record_response(
        self,
        *,
        quote_id: str,
        intent: str,
        body_text: str,
    ) -> QuoteResponseEventRecord:
        pass


class ShipmentWriteRepository(Protocol):
    async def get_shipment(self, shipment_id: str) -> ShipmentRecord | None:
        pass

    async def create_shipment(
        self,
        *,
        quote_id: str,
        carrier_id: str | None,
        lane: str,
        status: str,
        eta: str,
    ) -> ShipmentRecord:
        pass

    async def update_status(self, shipment_id: str, status: str) -> ShipmentRecord | None:
        pass


class InvoiceWriteRepository(Protocol):
    async def expected_invoice_amount(self, shipment_id: str) -> float:
        pass

    async def create_invoice_audit(
        self,
        *,
        shipment_id: str,
        invoice_amount: float,
        max_discrepancy: float,
    ) -> InvoiceRecord:
        pass


class OperationalTaskWriteRepository(Protocol):
    async def create_task(
        self,
        *,
        entity_type: str,
        entity_id: str,
        reason: str,
        priority: str = "normal",
    ) -> OperationalTaskRecord:
        pass


class ShipmentEventRepository(Protocol):
    async def record_status_change(
        self,
        *,
        shipment_id: str,
        from_status: str | None,
        to_status: str,
        reason: str | None = None,
    ) -> ShipmentEventRecord:
        pass


class OutboundReplyRepository(Protocol):
    async def enqueue_quote(
        self,
        *,
        quote_id: str,
        recipient: str,
        subject: str,
        body_text: str,
    ) -> OutboundReplyRecord:
        pass

    async def next_queued(self, limit: int) -> list[OutboundReplyRecord]:
        pass

    async def mark_sent(self, reply_id: str) -> OutboundReplyRecord:
        pass

    async def mark_failed(self, reply_id: str, error_message: str) -> OutboundReplyRecord:
        pass


class OutboundMailer(Protocol):
    async def send(self, reply: OutboundReplyRecord) -> None:
        pass


class RateProfileRepository(Protocol):
    async def find_matching(
        self, *, mode: str, origin: str | None, destination: str | None
    ) -> RateProfileRecord | None:
        pass

    async def list_all(self) -> list[RateProfileRecord]:
        pass

    async def create(
        self,
        *,
        mode: str,
        origin: str | None,
        destination: str | None,
        base_price: float,
        price_per_kg: float,
        currency: str,
    ) -> RateProfileRecord:
        pass

    async def update(
        self,
        rate_profile_id: str,
        *,
        mode: str,
        origin: str | None,
        destination: str | None,
        base_price: float,
        price_per_kg: float,
        currency: str,
    ) -> RateProfileRecord:
        pass
