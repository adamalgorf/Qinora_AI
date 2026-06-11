from fastapi import Depends, FastAPI, Header, HTTPException, Request, status

from qinora.application import (
    AuthContext,
    CargoLineCommand,
    CarrierIntelligenceCommand,
    CreateRequestCommand,
    CreateRequestUseCase,
    EmailWebhookCommand,
    EmailWebhookUseCase,
    OperationalQueries,
    Role,
)
from qinora.infrastructure.in_memory import RecordingAgentDispatcher
from qinora.infrastructure.settings import Settings
from qinora.infrastructure.sqlite import (
    SQLiteDatabase,
    SQLiteInboundEmailRepository,
    SQLiteOperationalReadRepository,
    SQLiteRequestWriteRepository,
    SQLiteWebhookEventRepository,
)
from qinora.interfaces.http.auth import get_auth_context, require_roles
from qinora.interfaces.http.schemas import (
    AgentLogListItem,
    AuthMeResponse,
    CarrierIntelligenceRequest,
    CarrierIntelligenceResponse,
    CarrierListItem,
    CreateRequestPayload,
    CreateRequestResponse,
    DashboardSummaryResponse,
    EmailWebhookPayload,
    EmailWebhookResponse,
    InboxListItem,
    QuoteListItem,
    RequestListItem,
    ShipmentListItem,
)
from qinora.interfaces.http.security import verify_hmac_signature

AUTH_CONTEXT = Depends(get_auth_context)


def create_app() -> FastAPI:
    app = FastAPI(title="QiNora TMS API", version="0.1.0")
    settings = Settings.from_env()
    database = SQLiteDatabase(settings.sqlite_path)
    dispatcher = RecordingAgentDispatcher()
    email_webhook = EmailWebhookUseCase(
        SQLiteWebhookEventRepository(database),
        SQLiteInboundEmailRepository(database),
        dispatcher,
    )
    operational_queries = OperationalQueries(SQLiteOperationalReadRepository(database))
    create_request = CreateRequestUseCase(SQLiteRequestWriteRepository(database))

    app.state.settings = settings
    app.state.database = database
    app.state.dispatcher = dispatcher
    app.state.email_webhook = email_webhook
    app.state.operational_queries = operational_queries
    app.state.create_request = create_request

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/auth/me", response_model=AuthMeResponse)
    async def auth_me(context: AuthContext = AUTH_CONTEXT) -> AuthMeResponse:
        return AuthMeResponse(
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            roles=[role.value for role in sorted(context.roles, key=lambda role: role.value)],
        )

    @app.get("/dashboard/summary", response_model=DashboardSummaryResponse)
    async def dashboard_summary(request: Request) -> DashboardSummaryResponse:
        queries: OperationalQueries = request.app.state.operational_queries
        summary = await queries.dashboard_summary()
        return DashboardSummaryResponse.model_validate(summary.__dict__)

    @app.get("/requests", response_model=list[RequestListItem])
    async def list_requests(request: Request) -> list[RequestListItem]:
        queries: OperationalQueries = request.app.state.operational_queries
        return [RequestListItem(**item.__dict__) for item in await queries.list_requests()]

    @app.post(
        "/requests",
        response_model=CreateRequestResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_transport_request(
        payload: CreateRequestPayload,
        request: Request,
        context: AuthContext = AUTH_CONTEXT,
    ) -> CreateRequestResponse:
        require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
        use_case: CreateRequestUseCase = request.app.state.create_request
        result = await use_case.execute(
            CreateRequestCommand(
                customer=payload.customer,
                origin=payload.origin,
                destination=payload.destination,
                mode=payload.mode,
                loading_time=payload.loading_time,
                unloading_time=payload.unloading_time,
                cargo=tuple(
                    CargoLineCommand(
                        description=line.description,
                        quantity=line.quantity,
                        weight_kg=line.weight_kg,
                        length_cm=line.length_cm,
                        width_cm=line.width_cm,
                        height_cm=line.height_cm,
                    )
                    for line in payload.cargo
                ),
            )
        )

        return CreateRequestResponse(
            request=RequestListItem(**result.request.__dict__),
            complete=result.complete,
            review_reason=result.review_reason,
            adr_un_numbers=list(result.adr_un_numbers),
        )

    @app.get("/quotes", response_model=list[QuoteListItem])
    async def list_quotes(request: Request) -> list[QuoteListItem]:
        queries: OperationalQueries = request.app.state.operational_queries
        return [QuoteListItem(**item.__dict__) for item in await queries.list_quotes()]

    @app.get("/shipments", response_model=list[ShipmentListItem])
    async def list_shipments(request: Request) -> list[ShipmentListItem]:
        queries: OperationalQueries = request.app.state.operational_queries
        return [ShipmentListItem(**item.__dict__) for item in await queries.list_shipments()]

    @app.get("/carriers", response_model=list[CarrierListItem])
    async def list_carriers(request: Request) -> list[CarrierListItem]:
        queries: OperationalQueries = request.app.state.operational_queries
        return [
            CarrierListItem(
                id=item.id,
                display_name=item.display_name,
                modes=list(item.modes),
                lane_score=item.lane_score,
                performance_score=item.performance_score,
                preferred=item.preferred,
            )
            for item in await queries.list_carriers()
        ]

    @app.post("/carriers/intelligence", response_model=CarrierIntelligenceResponse)
    async def run_carrier_intelligence(
        payload: CarrierIntelligenceRequest,
        request: Request,
        context: AuthContext = AUTH_CONTEXT,
    ) -> CarrierIntelligenceResponse:
        require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
        queries: OperationalQueries = request.app.state.operational_queries
        result = await queries.run_carrier_intelligence(
            CarrierIntelligenceCommand(
                mode=payload.mode,
                total_weight_kg=payload.total_weight_kg,
                requested_carrier_name=payload.requested_carrier_name,
                min_confidence=payload.min_confidence,
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
        queries: OperationalQueries = request.app.state.operational_queries
        return [InboxListItem(**item.__dict__) for item in await queries.list_inbox()]

    @app.get("/agents/logs", response_model=list[AgentLogListItem])
    async def agent_logs(
        request: Request,
        context: AuthContext = AUTH_CONTEXT,
    ) -> list[AgentLogListItem]:
        require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
        queries: OperationalQueries = request.app.state.operational_queries
        return [AgentLogListItem(**item.__dict__) for item in await queries.list_agent_logs()]

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
        settings: Settings = request.app.state.settings
        body = await request.body()

        if not verify_hmac_signature(settings.email_webhook_secret, body, signature):
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
