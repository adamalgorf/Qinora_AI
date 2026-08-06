from dataclasses import dataclass
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


@dataclass(frozen=True)
class AgentLogRecord:
    agent_key: str
    agent_name: str
    step: str
    entity_id: str
    confidence: float


@dataclass(frozen=True)
class AgentConfigRecord:
    agent_key: str
    agent_name: str
    is_enabled: bool
    auto_mode: str
    min_confidence: float


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


@dataclass(frozen=True)
class QuoteResponseEventRecord:
    id: str
    quote_id: str
    intent: str
    body_text: str
    created_at: str
