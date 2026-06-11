from dataclasses import dataclass


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
class QuoteRecord:
    id: str
    status: str
    version: int
    customer_price: float
    currency: str
    parent_quote_id: str | None


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
class AgentLogRecord:
    agent_key: str
    agent_name: str
    step: str
    entity_id: str
    confidence: float


@dataclass(frozen=True)
class InboxRecord:
    id: str
    sender: str
    subject: str
    received_at: str
    classification: str
