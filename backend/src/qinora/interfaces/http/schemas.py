from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class EmailWebhookPayload(BaseModel):
    sender: EmailStr
    subject: str = Field(min_length=1, max_length=500)
    body_text: str = Field(min_length=1)


class EmailWebhookResponse(BaseModel):
    accepted: bool
    duplicate: bool
    inbound_email_id: str | None = None


class AuthMeResponse(BaseModel):
    user_id: str
    tenant_id: str
    roles: list[str]


class DevTokenRequest(BaseModel):
    user_id: str = "dev-user"
    tenant_id: str = "dev-tenant"
    roles: list[str] = Field(default_factory=lambda: ["admin"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthMeResponse


class AuthConfigResponse(BaseModel):
    login_required: bool


class LoginRequest(BaseModel):
    password: str = Field(min_length=1)


class KpiItem(BaseModel):
    label: str
    value: str
    trend: str


class PipelineItem(BaseModel):
    status: str
    count: int


class AgentActivityItem(BaseModel):
    agent: str
    event: str
    confidence: float


class DashboardSummaryResponse(BaseModel):
    kpis: list[KpiItem]
    pipeline: list[PipelineItem]
    agent_activity: list[AgentActivityItem] = Field(serialization_alias="agentActivity")


class RequestListItem(BaseModel):
    id: str
    public_id: str
    customer: str
    lane: str
    mode: str
    status: str
    weight_kg: float


class CargoLinePayload(BaseModel):
    description: str = Field(min_length=1)
    quantity: int | None = Field(default=None, ge=1)
    weight_kg: float | None = Field(default=None, gt=0)
    length_cm: float | None = Field(default=None, gt=0)
    width_cm: float | None = Field(default=None, gt=0)
    height_cm: float | None = Field(default=None, gt=0)


class CreateRequestPayload(BaseModel):
    customer: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    mode: Literal["ftl", "ltl", "ocean", "air", "rail", "intermodal"]
    cargo: list[CargoLinePayload] = Field(min_length=1)
    loading_time: datetime | None = None
    unloading_time: datetime | None = None


class CreateRequestResponse(BaseModel):
    request: RequestListItem
    complete: bool
    review_reason: str | None
    adr_un_numbers: list[str]


class ParseFreeTextRequestPayload(BaseModel):
    customer: str = Field(min_length=1)
    raw_text: str = Field(min_length=1, description="Free-text RFQ/request, e.g. an email body")


class ParsedCargoLinePayload(BaseModel):
    description: str
    quantity: int | None = None
    weight_kg: float | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None


class ParsedRequestDraftPayload(BaseModel):
    mode: str
    origin: str
    destination: str
    cargo: list[ParsedCargoLinePayload]
    loading_time: datetime | None
    unloading_time: datetime | None
    confidence: float
    missing_fields: list[str]


class ParseFreeTextRequestResponse(BaseModel):
    draft: ParsedRequestDraftPayload
    needs_human_review: bool
    request: RequestListItem | None
    agent_confidence: float


class ParseCarrierOfferPayload(BaseModel):
    raw_text: str = Field(min_length=1, description="Free-text carrier reply, e.g. an email body")


class ParsedCarrierOfferPayload(BaseModel):
    carrier_name: str
    price: float | None = None
    currency: str | None = None
    transit_days: int | None = None
    notes: str | None = None
    confidence: float
    missing_fields: list[str]


class CarrierOfferItem(BaseModel):
    id: str
    request_id: str
    carrier_name: str
    price: float | None
    currency: str | None
    transit_days: int | None
    notes: str | None
    confidence: float
    created_at: str


class ParseCarrierOfferResponse(BaseModel):
    draft: ParsedCarrierOfferPayload
    needs_human_review: bool
    offer: CarrierOfferItem | None
    agent_confidence: float


class QuoteListItem(BaseModel):
    id: str
    status: str
    version: int
    customer_price: float
    currency: str
    parent_quote_id: str | None = None
    request_id: str | None = None


class QuoteLineItem(BaseModel):
    id: str
    quote_id: str
    description: str
    amount: float
    currency: str


class QuoteAcceptanceEventItem(BaseModel):
    id: str
    quote_id: str
    event_type: str
    detail: str
    created_at: str


class QuoteDetailResponse(BaseModel):
    quote: QuoteListItem
    line_items: list[QuoteLineItem]
    acceptance_events: list[QuoteAcceptanceEventItem]


class SearchResultItem(BaseModel):
    id: str
    public_id: str
    entity_type: str
    label: str
    description: str
    href: str


class OutboundReplyItem(BaseModel):
    id: str
    quote_id: str
    recipient: str
    subject: str
    body_text: str
    status: str
    created_at: str
    sent_at: str | None = None
    error_message: str | None = None


class SendQuoteResponse(BaseModel):
    quote: QuoteListItem
    outbound_reply: OutboundReplyItem


class QuoteReplyPayload(BaseModel):
    body_text: str = Field(min_length=1)
    mode: str = "ltl"
    total_weight_kg: float = 820
    requested_carrier_name: str | None = "Nordic"
    min_confidence: float = 0.65
    revised_customer_price: float | None = None


class QuoteResponseEventItem(BaseModel):
    id: str
    quote_id: str
    intent: str
    body_text: str
    created_at: str


class QuoteReplyResponse(BaseModel):
    intent: str
    event: QuoteResponseEventItem
    quote: QuoteListItem | None = None
    revised_quote: QuoteListItem | None = None
    shipment: ShipmentListItem | None = None


class ProcessOutboundQueuePayload(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)


class ProcessOutboundQueueResponse(BaseModel):
    sent: list[OutboundReplyItem]
    failed: list[OutboundReplyItem]


class DemoFlowResponse(BaseModel):
    steps: list[str]
    request: RequestListItem
    quote: QuoteListItem
    outbound_reply: OutboundReplyItem
    shipment: ShipmentListItem
    invoice: InvoiceListItem
    shipment_status: str


class CreateQuotePayload(BaseModel):
    request_id: str
    customer_price: float
    currency: str = "SEK"


class ShipmentListItem(BaseModel):
    id: str
    public_id: str
    quote_id: str
    carrier_id: str | None
    lane: str
    status: str
    eta: str


class InvoiceListItem(BaseModel):
    id: str
    public_id: str
    shipment_id: str
    quote_id: str
    invoice_amount: float
    quote_amount: float
    currency: str
    status: str
    discrepancy_amount: float


class CreateInvoicePayload(BaseModel):
    invoice_amount: float
    max_discrepancy: float = 250


class CreateInvoiceResponse(BaseModel):
    invoice: InvoiceListItem
    shipment_status: str


class RunTrackingSimulatorPayload(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)
    max_discrepancy: float = 250


class RunTrackingSimulatorResponse(BaseModel):
    delivered: list[ShipmentListItem]
    invoices: list[InvoiceListItem]


class AcceptQuotePayload(BaseModel):
    mode: str = "ftl"
    total_weight_kg: float
    requested_carrier_name: str | None = None
    min_confidence: float = 0.65


class AcceptQuoteResponse(BaseModel):
    shipment: ShipmentListItem
    selected_carrier_id: str | None
    requires_manual_review: bool
    overall_confidence: float


class UpdateShipmentStatusPayload(BaseModel):
    status: str


class OverrideShipmentPayload(BaseModel):
    status: str
    reason: str = Field(min_length=3, max_length=500)


class CarrierListItem(BaseModel):
    id: str
    display_name: str
    modes: list[str]
    lane_score: float
    performance_score: float | None
    preferred: bool


class ContactListItem(BaseModel):
    id: str
    public_id: str
    display_name: str
    email: str | None
    domain: str | None
    default_markup_percent: float
    default_incoterms: str | None
    payment_terms: str | None


class InboxListItem(BaseModel):
    id: str
    sender: str
    subject: str
    received_at: str
    classification: str


class AgentLogListItem(BaseModel):
    agent_key: str
    agent_name: str
    step: str
    entity_id: str
    confidence: float


class AgentConfigItem(BaseModel):
    agent_key: str
    agent_name: str
    is_enabled: bool
    auto_mode: Literal["manual", "assisted", "guarded_auto"]
    min_confidence: float


class UpdateAgentConfigPayload(BaseModel):
    is_enabled: bool
    auto_mode: Literal["manual", "assisted", "guarded_auto"]
    min_confidence: float = Field(ge=0, le=1)


class OperationalTaskItem(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    priority: str
    reason: str
    status: str
    created_at: str


class ShipmentEventItem(BaseModel):
    id: str
    shipment_id: str
    from_status: str | None
    to_status: str
    reason: str | None
    created_at: str


class CarrierIntelligenceRequest(BaseModel):
    mode: str
    total_weight_kg: float
    requested_carrier_name: str | None = None
    min_confidence: float = 0.65


class CarrierEvaluationItem(BaseModel):
    carrier_id: str
    rank: int
    status: str
    score_total: float
    reasons: list[str]


class CarrierIntelligenceResponse(BaseModel):
    selected_carrier_id: str | None
    requires_manual_review: bool
    overall_confidence: float
    evaluations: list[CarrierEvaluationItem]
