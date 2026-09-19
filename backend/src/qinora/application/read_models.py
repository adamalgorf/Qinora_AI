from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True)
class ParsedCargoLine:
    description: str
    quantity: int | None
    weight_kg: float | None
    length_cm: float | None
    width_cm: float | None
    height_cm: float | None


@dataclass(frozen=True)
class ParsedTransportRequestDraft:
    """Output of a RequestParsingLLM implementation (see application/ports.py).

    Framework-agnostic on purpose: neither this dataclass nor anything that
    consumes it (RequestParsingAgent) knows OpenAI exists. Only the
    infrastructure adapter does.
    """

    mode: str
    origin: str
    destination: str
    cargo: tuple[ParsedCargoLine, ...]
    loading_time: datetime | None
    unloading_time: datetime | None
    confidence: float
    missing_fields: tuple[str, ...]
    action: str = "create"


@dataclass(frozen=True)
class ParsedCarrierOfferDraft:
    """Output of a CarrierOfferParsingLLM implementation - a carrier's
    free-text reply, extracted into a structured rate offer.
    """

    carrier_name: str
    price: float | None
    currency: str | None
    transit_days: int | None
    notes: str | None
    confidence: float
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class CarrierOfferRecord:
    id: str
    request_id: str
    carrier_name: str
    price: float | None
    currency: str | None
    transit_days: int | None
    notes: str | None
    confidence: float
    created_at: str
    # Links this offer to the carrier_rfqs row it was collected for (see
    # application/carrier_rfq_collector.py) - None for offers that arrived
    # outside the automatic RFQ flow (e.g. a manual booking-time reply).
    carrier_rfq_id: str | None = None


class QuoteReplyIntent(StrEnum):
    ACCEPTED = "accepted"
    REVISE = "revise"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class QuoteReplyInterpretation:
    """Output of a QuoteReplyInterpretationLLM implementation."""

    intent: QuoteReplyIntent
    revised_price: float | None
    confidence: float


@dataclass(frozen=True)
class RequestRecord:
    id: str
    public_id: str
    customer: str
    lane: str
    mode: str
    status: str
    weight_kg: float
    # Case-view fields added by migrations/0011_case_fields.sql - composed
    # over transport_requests, not a separate "cases" table. Defaulted so
    # every existing construction site (create/update_transport_request,
    # tests, seed data) keeps working unchanged.
    assignee: str | None = None
    sla_due_at: str | None = None
    priority: str = "normal"


@dataclass(frozen=True)
class RequestCargoLineRecord:
    id: str
    description: str
    quantity: int | None
    weight_kg: float | None
    length_cm: float | None
    width_cm: float | None
    height_cm: float | None
    hazardous: bool
    un_number: str | None


@dataclass(frozen=True)
class RequestDetailRecord:
    request: RequestRecord
    review_reason: str | None
    created_at: str
    cargo_lines: tuple[RequestCargoLineRecord, ...]


@dataclass(frozen=True)
class StaleRequestRecord:
    id: str
    public_id: str
    customer: str
    review_reason: str | None
    created_at: str


@dataclass(frozen=True)
class QuoteRecord:
    id: str
    status: str
    version: int
    customer_price: float
    currency: str
    parent_quote_id: str | None
    request_id: str | None = None
    # Display context, filled in by list_quotes only: who ordered the
    # transport, the lane, and which carrier runs it - the booked shipment's
    # carrier if booked, else the carrier whose RFQ offer priced the quote.
    # None when not known yet (e.g. rate-profile quote not booked yet).
    customer: str | None = None
    lane: str | None = None
    carrier_name: str | None = None


@dataclass(frozen=True)
class QuoteLineItemRecord:
    id: str
    quote_id: str
    description: str
    amount: float
    currency: str


@dataclass(frozen=True)
class QuoteAcceptanceEventRecord:
    id: str
    quote_id: str
    event_type: str
    detail: str
    created_at: str


@dataclass(frozen=True)
class QuoteDetailRecord:
    quote: QuoteRecord
    line_items: tuple[QuoteLineItemRecord, ...]
    acceptance_events: tuple[QuoteAcceptanceEventRecord, ...]


@dataclass(frozen=True)
class SearchResultRecord:
    id: str
    public_id: str
    entity_type: str
    label: str
    description: str
    href: str


@dataclass(frozen=True)
class ShipmentRecord:
    id: str
    public_id: str
    quote_id: str
    carrier_id: str | None
    lane: str
    status: str
    eta: str


@dataclass(frozen=True)
class InvoiceRecord:
    id: str
    public_id: str
    shipment_id: str
    quote_id: str
    invoice_amount: float
    quote_amount: float
    currency: str
    status: str
    discrepancy_amount: float


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str
    full_name: str | None
    roles: tuple[str, ...]
    is_active: bool
    password_hash: str


@dataclass(frozen=True)
class CarrierRecord:
    id: str
    display_name: str
    aliases: tuple[str, ...]
    modes: tuple[str, ...]
    lane_score: float
    max_weight_kg: float | None
    performance_score: float | None
    preferred: bool
    sample_size: int
    # Carriers without an email are simply never picked as an automatic RFQ
    # target (application/carrier_rfq.py) - manual booking-time selection
    # (domain/carrier_intelligence.py's evaluate_carriers) is unaffected.
    email: str | None = None


@dataclass(frozen=True)
class ContactRecord:
    id: str
    public_id: str
    display_name: str
    email: str | None
    domain: str | None
    default_markup_percent: float
    default_incoterms: str | None
    payment_terms: str | None
    # Customer-profile fields added by migrations/0012_customer_profile_fields.sql.
    # All optional/defaulted so existing construction sites (list_contacts,
    # find_by_sender, tests) keep working unchanged.
    segment: str | None = None
    customer_since: str | None = None
    sla_tolerance_hours: float | None = None
    account_owner: str | None = None
    health_status: str = "good"
    contract_note: str | None = None
    customs_contact_name: str | None = None
    customs_contact_email: str | None = None
    annual_volume_estimate: float | None = None


@dataclass(frozen=True)
class ContactDetailRecord:
    """GET /contacts/{id} - a contact plus best-effort operational signals.

    active_jobs/active_route are derived from shipments joined back to this
    contact via transport_requests.customer == contacts.display_name, since
    no adapter in this codebase ever populates a contact_id FK on
    transport_requests (see infrastructure/postgres.py's
    PostgresOperationalReadRepository.get_contact_detail for the join and a
    fuller note). avg_ai_response_minutes is None when no inbound email for
    this contact was ever threaded to a request - never fabricated.
    """

    contact: ContactRecord
    active_jobs: int
    active_route: str | None
    avg_ai_response_minutes: float | None


@dataclass(frozen=True)
class AgentLogRecord:
    agent_key: str
    agent_name: str
    step: str
    entity_id: str
    confidence: float
    # Populated by list_agent_logs() (both adapters) so analytics_summary()'s
    # workload_by_weekday grouping and the Cases activity feed's timestamp
    # sort have something to key off - the agent_logs table already had this
    # column, it just wasn't surfaced on the record before. Empty string
    # default keeps AgentLogWriteRepository.record()'s call sites (which
    # don't round-trip through a SELECT) working unchanged.
    created_at: str = ""


@dataclass(frozen=True)
class AgentConfigRecord:
    agent_key: str
    agent_name: str
    is_enabled: bool
    auto_mode: str
    min_confidence: float
    config: dict = field(default_factory=dict)


@dataclass(frozen=True)
class InboxRecord:
    id: str
    sender: str
    subject: str
    received_at: str
    classification: str


@dataclass(frozen=True)
class InboxDetailRecord:
    message: InboxRecord
    body_text: str


@dataclass(frozen=True)
class OperationalTaskRecord:
    id: str
    entity_type: str
    entity_id: str
    priority: str
    reason: str
    status: str
    created_at: str


@dataclass(frozen=True)
class ShipmentEventRecord:
    id: str
    shipment_id: str
    from_status: str | None
    to_status: str
    reason: str | None
    created_at: str


@dataclass(frozen=True)
class OutboundReplyRecord:
    id: str
    quote_id: str
    recipient: str
    subject: str
    body_text: str
    status: str
    created_at: str
    sent_at: str | None = None
    error_message: str | None = None
    # RFC822 Message-ID of the inbound email this is a reply to, if any - so
    # the Gmail bridge can send it as an actual in-thread reply
    # (GmailThread.reply()) instead of a new top-level email. See
    # integrations/gmail-intake-bridge/Code.gs's sendQueuedReplies().
    in_reply_to_message_id: str | None = None
    # Which mailbox should send this (e.g. "test.spedition@sandahls.com") -
    # None means "any bridge instance may send it" (legacy rows, and
    # deployments with only one mailbox). See workers/outlook_bridge.py's
    # per-instance filtering when more than one bridge instance is running,
    # each authenticated as a different mailbox.
    sender_mailbox: str | None = None


@dataclass(frozen=True)
class QuoteResponseEventRecord:
    id: str
    quote_id: str
    intent: str
    body_text: str
    created_at: str


@dataclass(frozen=True)
class InboundEmailRecord:
    """A single email_inbound row, including the threading columns added
    for the email intake orchestrator (see application/thread_matching.py
    and application/email_intake_orchestrator.py). Doubles as both the
    "fetch one email" read shape and a thread-matching candidate row.
    """

    id: str
    sender: str
    recipient: str
    subject: str
    body_text: str
    classification: str | None
    message_id: str | None
    in_reply_to: str | None
    references_header: str | None
    request_id: str | None
    quote_id: str | None
    created_at: str
    sender_name: str | None = None


@dataclass(frozen=True)
class RateProfileRecord:
    id: str
    mode: str
    origin: str | None
    destination: str | None
    base_price: float
    price_per_kg: float
    currency: str


@dataclass(frozen=True)
class CarrierRfqRecord:
    """One carrier's leg of an automatic RFQ batch (application/pricing_engine.py's
    carrier-sourcing branch + application/carrier_rfq_collector.py). status is
    one of 'sent' (awaiting reply), 'responded' (offer parsed and linked),
    'expired' (sourcing window elapsed with no reply) or 'superseded' (a
    cheaper reply in the same batch won instead).
    """

    id: str
    request_id: str
    carrier_id: str
    correlation_token: str
    status: str
    sent_at: str
    responded_at: str | None
    expires_at: str


@dataclass(frozen=True)
class CarrierRfqOutboundRecord:
    """Mirrors OutboundReplyRecord's shape but keyed to a carrier_rfq instead
    of a quote - kept as a separate queue/table so the already-shipped
    customer-quote outbound path never needs to tolerate a null quote_id.
    """

    id: str
    carrier_rfq_id: str
    recipient: str
    subject: str
    body_text: str
    status: str
    created_at: str
    sent_at: str | None = None
    error_message: str | None = None
    sender_mailbox: str | None = None


@dataclass(frozen=True)
class CarrierOfferReportOutboundRecord:
    """Mirrors CarrierRfqOutboundRecord's shape but keyed to the request the
    winning carrier offer belongs to, sent from the carrier mailbox (e.g.
    qinora.ai@sandahls.com) to the customer mailbox (e.g.
    test.spedition@sandahls.com) - the explicit "carrier desk reports the
    rate to the customer desk" email hop application/carrier_rfq_collector.py
    triggers once a batch's cheapest offer is known, mirrored on the
    receiving end by application/email_intake_orchestrator.py's offer-report
    detection, which is what actually creates and sends the customer-facing
    quote (see application/quote_workflow.py). Two real mailboxes, two real
    emails, not one internal function call - see carrier_rfq_collector.py's
    module docstring for why this hop exists at all.
    """

    id: str
    request_id: str
    recipient: str
    subject: str
    body_text: str
    status: str
    created_at: str
    sent_at: str | None = None
    error_message: str | None = None
    sender_mailbox: str | None = None


@dataclass(frozen=True)
class ClarificationOutboundRecord:
    """Mirrors CarrierRfqOutboundRecord's shape but keyed to the inbound
    email that Nora couldn't act on unassisted (missing required fields) -
    a separate queue/table for the same reason carrier_rfq_outbound is: it
    isn't tied to a quote, so it can't reuse outbound_reply_queue.
    """

    id: str
    inbound_email_id: str
    recipient: str
    subject: str
    body_text: str
    status: str
    created_at: str
    sent_at: str | None = None
    error_message: str | None = None
    in_reply_to_message_id: str | None = None
    sender_mailbox: str | None = None


@dataclass(frozen=True)
class DocumentRecord:
    """One documents row (migrations/0010_documents.sql), minus the raw
    bytes - used for list/detail metadata everywhere except
    get_document_content().
    """

    id: str
    public_id: str
    filename: str
    content_type: str
    size_bytes: int
    document_type: str | None
    status: str
    ai_confidence: float | None
    request_id: str | None
    shipment_id: str | None
    contact_id: str | None
    created_at: str


@dataclass(frozen=True)
class DocumentDetailRecord:
    document: DocumentRecord
    extracted_fields: dict


@dataclass(frozen=True)
class DocumentContentRecord:
    """The raw bytes for GET /documents/{id}/content, kept separate from
    DocumentRecord so a plain list_documents()/get_document() call never
    pulls a potentially-8MB bytea/BLOB column off the wire.
    """

    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class CaseNoteRecord:
    id: str
    request_id: str
    author: str
    body_text: str
    created_at: str
