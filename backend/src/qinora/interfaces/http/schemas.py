from pydantic import BaseModel, EmailStr, Field


class EmailWebhookPayload(BaseModel):
    sender: EmailStr
    subject: str = Field(min_length=1, max_length=500)
    body_text: str = Field(min_length=1)


class EmailWebhookResponse(BaseModel):
    accepted: bool
    duplicate: bool
    inbound_email_id: str | None = None


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


class QuoteListItem(BaseModel):
    id: str
    status: str
    version: int
    customer_price: float
    currency: str
    parent_quote_id: str | None = None


class ShipmentListItem(BaseModel):
    id: str
    public_id: str
    quote_id: str
    carrier_id: str | None
    lane: str
    status: str
    eta: str


class CarrierListItem(BaseModel):
    id: str
    display_name: str
    modes: list[str]
    lane_score: float
    performance_score: float | None
    preferred: bool


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
