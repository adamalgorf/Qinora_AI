import os

from fastapi import FastAPI, Header, HTTPException, Request, status

from qinora.application import EmailWebhookCommand, EmailWebhookUseCase
from qinora.infrastructure.in_memory import (
    InMemoryInboundEmailRepository,
    InMemoryWebhookEventRepository,
    RecordingAgentDispatcher,
)
from qinora.interfaces.http.schemas import EmailWebhookPayload, EmailWebhookResponse
from qinora.interfaces.http.security import verify_hmac_signature


def create_app() -> FastAPI:
    app = FastAPI(title="QiNora TMS API", version="0.1.0")
    webhook_events = InMemoryWebhookEventRepository()
    inbound_emails = InMemoryInboundEmailRepository()
    dispatcher = RecordingAgentDispatcher()
    email_webhook = EmailWebhookUseCase(webhook_events, inbound_emails, dispatcher)

    app.state.webhook_events = webhook_events
    app.state.inbound_emails = inbound_emails
    app.state.dispatcher = dispatcher
    app.state.email_webhook = email_webhook

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/dashboard/summary")
    async def dashboard_summary() -> dict[str, object]:
        return {
            "kpis": [
                {"label": "Open requests", "value": "23", "trend": "+12%"},
                {"label": "On-time", "value": "96%", "trend": "+3%"},
                {"label": "Exceptions", "value": "4", "trend": "-18%"},
                {"label": "Agent health", "value": "98%", "trend": "+1%"},
            ],
            "pipeline": [
                {"status": "New", "count": 8},
                {"status": "Parsing", "count": 3},
                {"status": "Quoted", "count": 12},
                {"status": "Booked", "count": 9},
                {"status": "In transit", "count": 17},
                {"status": "Needs review", "count": 4},
            ],
            "agentActivity": [
                {
                    "agent": "Nora Intake",
                    "event": "Classified inbound request",
                    "confidence": 0.94,
                },
                {
                    "agent": "Quinn Quote",
                    "event": "Pricing gate passed",
                    "confidence": 0.88,
                },
                {
                    "agent": "Carrier Intelligence",
                    "event": "Selected preferred carrier",
                    "confidence": 0.81,
                },
            ],
        }

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
