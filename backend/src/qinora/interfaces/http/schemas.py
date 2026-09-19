from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class EmailWebhookPayload(BaseModel):
    sender: EmailStr
    recipient: EmailStr
    subject: str = Field(min_length=1, max_length=500)
    body_text: str = Field(min_length=1)
    message_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    sender_name: str | None = None


class EmailWebhookResponse(BaseModel):
    accepted: bool
    duplicate: bool
    inbound_email_id: str | None = None


class AuthMeResponse(BaseModel):
    user_id: str
    tenant_id: str
    roles: list[str]
    full_name: str | None = None


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
    email: EmailStr
    password: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class UserListItem(BaseModel):
    id: str
    email: str
    full_name: str | None
    roles: list[str]
    is_active: bool


class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str | None = None
    roles: list[str] = Field(min_length=1)
    temporary_password: str = Field(min_length=8)


class UpdateUserRequest(BaseModel):
    roles: list[str] | None = None
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    temporary_password: str = Field(min_length=8)


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
    assignee: str | None = None
    sla_due_at: str | None = None
    priority: str = "normal"


class RequestCargoLineItem(BaseModel):
    id: str
    description: str
    quantity: int | None
    weight_kg: float | None
    length_cm: float | None
    width_cm: float | None
    height_cm: float | None
    hazardous: bool
    un_number: str | None


class RequestDetailResponse(BaseModel):
    request: RequestListItem
    review_reason: str | None
    created_at: str
    cargo_lines: list[RequestCargoLineItem]


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
    customer: str | None = None
    lane: str | None = None
    carrier_name: str | None = None


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
    reference: str
    line_items: list[QuoteLineItem]
    acceptance_events: list[QuoteAcceptanceEventItem]
    request: RequestDetailResponse | None = None
    sent_email: OutboundReplyItem | None = None


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


class CarrierCreateRequest(BaseModel):
    display_name: str = Field(min_length=1)
    modes: list[str] = Field(min_length=1, description="e.g. ['ftl', 'ltl']")
    aliases: list[str] = Field(default_factory=list)
    email: EmailStr | None = None
    lane_score: float = 50.0
    max_weight_kg: float | None = None
    performance_score: float | None = None
    preferred: bool = False


class ContactListItem(BaseModel):
    id: str
    public_id: str
    display_name: str
    email: str | None
    domain: str | None
    default_markup_percent: float
    default_incoterms: str | None
    payment_terms: str | None
    segment: str | None = None
    customer_since: str | None = None
    sla_tolerance_hours: float | None = None
    account_owner: str | None = None
    health_status: str = "good"
    contract_note: str | None = None
    customs_contact_name: str | None = None
    customs_contact_email: str | None = None
    annual_volume_estimate: float | None = None
    org_number: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None


class ContactCreateRequest(BaseModel):
    display_name: str = Field(min_length=1)
    email: str | None = None
    domain: str | None = None
    default_markup_percent: float = 0.0
    default_incoterms: str | None = None
    payment_terms: str | None = None
    segment: str | None = None
    customer_since: str | None = Field(default=None, description="YYYY-MM-DD")
    sla_tolerance_hours: float | None = None
    account_owner: str | None = None
    health_status: str = "good"
    contract_note: str | None = None
    customs_contact_name: str | None = None
    customs_contact_email: str | None = None
    annual_volume_estimate: float | None = None
    org_number: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None


class ContactImportIssue(BaseModel):
    row: int
    display_name: str | None
    reason: str


class ContactImportResponse(BaseModel):
    created: list[ContactListItem]
    skipped: list[ContactImportIssue]
    errors: list[ContactImportIssue]


class CustomerDetailResponse(ContactListItem):
    active_jobs: int
    active_route: str | None = None
    avg_ai_response_minutes: float | None = None


class InboxListItem(BaseModel):
    id: str
    sender: str
    subject: str
    received_at: str
    classification: str


class InboxDetailResponse(BaseModel):
    message: InboxListItem
    body_text: str


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


class RateProfileItem(BaseModel):
    id: str
    mode: str
    origin: str | None
    destination: str | None
    base_price: float
    price_per_kg: float
    currency: str


class RateProfilePayload(BaseModel):
    mode: Literal["ftl", "ltl", "ocean", "air", "rail", "intermodal"]
    origin: str | None = None
    destination: str | None = None
    base_price: float = Field(ge=0)
    price_per_kg: float = Field(ge=0)
    currency: str = "SEK"


class OutboundQueueItem(BaseModel):
    """One row from outbound_reply_queue, carrier_rfq_outbound, or
    clarification_outbound, normalized to a common shape - see
    interfaces/http/routers/outbound.py.
    """

    queue: Literal["quote", "carrier_rfq", "clarification", "carrier_offer_report"]
    id: str
    recipient: str
    subject: str
    body_text: str
    in_reply_to_message_id: str | None = None
    # Which mailbox this item should be sent from, when more than one
    # Outlook bridge instance is running - see workers/outlook_bridge.py.
    # None means "any bridge instance may send it".
    sender_mailbox: str | None = None


class OutboundAckResponse(BaseModel):
    ok: bool = True


class OutboundFailPayload(BaseModel):
    error_message: str = Field(min_length=1, max_length=2000)


class CollectCarrierRfqsResponse(BaseModel):
    finalized: int
    escalated: int


class DocumentListItem(BaseModel):
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


class DocumentDetailResponse(BaseModel):
    document: DocumentListItem
    extracted_fields: dict


class CreateDocumentResponse(DocumentListItem):
    pass


class CaseListItem(BaseModel):
    id: str
    public_id: str
    customer: str
    category: str
    lane: str
    priority: str
    sla_due_at: str | None
    assignee: str | None
    status: str


class CaseActivityItem(BaseModel):
    type: str
    timestamp: str | None
    tag: str
    description: str


class CaseEmailItem(BaseModel):
    direction: Literal["inbound", "outbound"]
    kind: Literal["customer", "carrier", "quote", "clarification", "booking_confirmation"]
    timestamp: str | None
    sender: str
    recipient: str
    subject: str
    body_text: str


class InternalNoteItem(BaseModel):
    id: str
    request_id: str
    author: str
    body_text: str
    created_at: str


class CaseDetailResponse(BaseModel):
    case: CaseListItem
    request_detail: RequestDetailResponse
    quotes: list[QuoteListItem]
    shipment: ShipmentListItem | None
    invoice: InvoiceListItem | None
    documents: list[DocumentListItem]
    contact: ContactListItem | None
    notes: list[InternalNoteItem]
    activity: list[CaseActivityItem]
    emails: list[CaseEmailItem]


class CreateCaseNotePayload(BaseModel):
    author: str = Field(min_length=1)
    body_text: str = Field(min_length=1)


class AutomationListItem(BaseModel):
    agent_key: str
    agent_name: str
    trigger: str
    scope: str
    success_rate: float
    volume: int
    status: str


class AnalyticsKpiItem(BaseModel):
    label: str
    value: str
    trend: str


class WorkloadByWeekdayItem(BaseModel):
    weekday: str
    ai: int
    manual: int


class ExceptionCategoryItem(BaseModel):
    category: str
    percent: float
    location: str | None = None


class AnalyticsSummaryResponse(BaseModel):
    kpis: list[AnalyticsKpiItem]
    workload_by_weekday: list[WorkloadByWeekdayItem]
    top_exception_categories: list[ExceptionCategoryItem]
