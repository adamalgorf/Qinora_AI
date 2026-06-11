import os

from fastapi import FastAPI, Header, HTTPException, Request, status

from qinora.application import EmailWebhookCommand, EmailWebhookUseCase
from qinora.domain import CarrierEvaluationInput, TransportMode, evaluate_carriers
from qinora.infrastructure.in_memory import (
    InMemoryInboundEmailRepository,
    InMemoryWebhookEventRepository,
    RecordingAgentDispatcher,
)
from qinora.infrastructure.seed_data import SeedDataStore
from qinora.interfaces.http.schemas import (
    AgentActivityItem,
    AgentLogListItem,
    CarrierIntelligenceRequest,
    CarrierIntelligenceResponse,
    CarrierListItem,
    DashboardSummaryResponse,
    EmailWebhookPayload,
    EmailWebhookResponse,
    InboxListItem,
    KpiItem,
    PipelineItem,
    QuoteListItem,
    RequestListItem,
    ShipmentListItem,
)
from qinora.interfaces.http.security import verify_hmac_signature


def create_app() -> FastAPI:
    app = FastAPI(title="QiNora TMS API", version="0.1.0")
    webhook_events = InMemoryWebhookEventRepository()
    inbound_emails = InMemoryInboundEmailRepository()
    dispatcher = RecordingAgentDispatcher()
    email_webhook = EmailWebhookUseCase(webhook_events, inbound_emails, dispatcher)
    data_store = SeedDataStore.create()

    app.state.webhook_events = webhook_events
    app.state.inbound_emails = inbound_emails
    app.state.dispatcher = dispatcher
    app.state.email_webhook = email_webhook
    app.state.data_store = data_store

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/dashboard/summary", response_model=DashboardSummaryResponse)
    async def dashboard_summary(request: Request) -> DashboardSummaryResponse:
        store: SeedDataStore = request.app.state.data_store
        open_requests = len([item for item in store.requests if item.status != "converted"])
        exceptions = len([item for item in store.shipments if item.status.value == "needs_review"])

        return DashboardSummaryResponse(
            kpis=[
                KpiItem(label="Open requests", value=str(open_requests), trend="+12%"),
                KpiItem(label="On-time", value="96%", trend="+3%"),
                KpiItem(label="Exceptions", value=str(exceptions), trend="-18%"),
                KpiItem(label="Agent health", value="98%", trend="+1%"),
            ],
            pipeline=[
                PipelineItem(status="New", count=8),
                PipelineItem(status="Parsing", count=3),
                PipelineItem(status="Quoted", count=12),
                PipelineItem(status="Booked", count=9),
                PipelineItem(status="In transit", count=17),
                PipelineItem(status="Needs review", count=exceptions),
            ],
            agent_activity=[
                AgentActivityItem(
                    agent=log.agent_name,
                    event=log.step,
                    confidence=log.confidence,
                )
                for log in store.agent_logs
            ],
        )

    @app.get("/requests", response_model=list[RequestListItem])
    async def list_requests(request: Request) -> list[RequestListItem]:
        store: SeedDataStore = request.app.state.data_store
        return [
            RequestListItem(
                id=item.id,
                public_id=item.public_id,
                customer=item.customer,
                lane=item.lane,
                mode=item.mode.value,
                status=item.status,
                weight_kg=item.weight_kg,
            )
            for item in store.requests
        ]

    @app.get("/quotes", response_model=list[QuoteListItem])
    async def list_quotes(request: Request) -> list[QuoteListItem]:
        store: SeedDataStore = request.app.state.data_store
        return [
            QuoteListItem(
                id=item.id,
                status=item.status.value,
                version=item.version,
                customer_price=item.customer_price.amount,
                currency=item.customer_price.currency.value,
                parent_quote_id=item.parent_quote_id,
            )
            for item in store.quotes
        ]

    @app.get("/shipments", response_model=list[ShipmentListItem])
    async def list_shipments(request: Request) -> list[ShipmentListItem]:
        store: SeedDataStore = request.app.state.data_store
        return [
            ShipmentListItem(
                id=item.id,
                public_id=item.public_id,
                quote_id=item.quote_id,
                carrier_id=item.carrier_id,
                lane=item.lane,
                status=item.status.value,
                eta=item.eta,
            )
            for item in store.shipments
        ]

    @app.get("/carriers", response_model=list[CarrierListItem])
    async def list_carriers(request: Request) -> list[CarrierListItem]:
        store: SeedDataStore = request.app.state.data_store
        return [
            CarrierListItem(
                id=item.id,
                display_name=item.display_name,
                modes=[mode.value for mode in item.modes],
                lane_score=item.lane_score,
                performance_score=item.performance_score,
                preferred=item.preferred,
            )
            for item in store.carriers
        ]

    @app.post("/carriers/intelligence", response_model=CarrierIntelligenceResponse)
    async def run_carrier_intelligence(
        payload: CarrierIntelligenceRequest, request: Request
    ) -> CarrierIntelligenceResponse:
        store: SeedDataStore = request.app.state.data_store
        result = evaluate_carriers(
            CarrierEvaluationInput(
                mode=TransportMode(payload.mode),
                total_weight_kg=payload.total_weight_kg,
                requested_carrier_name=payload.requested_carrier_name,
                min_confidence=payload.min_confidence,
                candidates=tuple(store.carriers),
            )
        )

        return CarrierIntelligenceResponse(
            selected_carrier_id=result.selected_carrier_id,
            requires_manual_review=result.requires_manual_review,
            overall_confidence=result.overall_confidence,
            evaluations=[
                {
                    "carrier_id": item.carrier_id,
                    "rank": item.rank,
                    "status": item.status,
                    "score_total": item.score_total,
                    "reasons": list(item.reasons),
                }
                for item in result.evaluations
            ],
        )

    @app.get("/inbox/pending", response_model=list[InboxListItem])
    async def pending_inbox(request: Request) -> list[InboxListItem]:
        store: SeedDataStore = request.app.state.data_store
        return [InboxListItem(**item.__dict__) for item in store.inbox]

    @app.get("/agents/logs", response_model=list[AgentLogListItem])
    async def agent_logs(request: Request) -> list[AgentLogListItem]:
        store: SeedDataStore = request.app.state.data_store
        return [AgentLogListItem(**item.__dict__) for item in store.agent_logs]

    @app.post(
        "/webhooks/email",
        response_model=EmailWebhookResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def email_webhook_route(
        request: Request,
        payload: EmailWebhookPayload,
        idempotency_key: str = Header(alias="x-idempotency-key"),
        signature: str | None = Header(default=None, alias="x-qinora-signature"),
    ) -> EmailWebhookResponse:
        secret = os.getenv("EMAIL_WEBHOOK_SECRET", "")
        body = await request.body()

        if not verify_hmac_signature(secret, body, signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )

        use_case: EmailWebhookUseCase = request.app.state.email_webhook
        result = await use_case.execute(
            EmailWebhookCommand(
                idempotency_key=idempotency_key,
                sender=str(payload.sender),
                subject=payload.subject,
                body_text=payload.body_text,
            )
        )

        return EmailWebhookResponse(
            accepted=result.accepted,
            duplicate=result.duplicate,
            inbound_email_id=result.inbound_email_id,
        )

    return app
