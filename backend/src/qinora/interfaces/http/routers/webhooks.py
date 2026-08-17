from fastapi import APIRouter, Header, HTTPException, Request, status

from qinora.application import EmailWebhookCommand
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import CONTAINER
from qinora.interfaces.http.schemas import EmailWebhookPayload, EmailWebhookResponse
from qinora.interfaces.http.security import verify_hmac_signature

router = APIRouter()


@router.post(
    "/webhooks/email",
    response_model=EmailWebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def email_webhook_route(
    request: Request,
    payload: EmailWebhookPayload,
    idempotency_key: str = Header(alias="x-idempotency-key"),
    signature: str | None = Header(default=None, alias="x-qinora-signature"),
    container: AppContainer = CONTAINER,
) -> EmailWebhookResponse:
    body = await request.body()

    if not verify_hmac_signature(container.settings.email_webhook_secret, body, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    result = await container.email_webhook.execute(
        EmailWebhookCommand(
            idempotency_key=idempotency_key,
            sender=str(payload.sender),
            subject=payload.subject,
            body_text=payload.body_text,
            recipient=str(payload.recipient),
            message_id=payload.message_id,
            in_reply_to=payload.in_reply_to,
            references=payload.references,
            sender_name=payload.sender_name,
        )
    )

    return EmailWebhookResponse(
        accepted=result.accepted,
        duplicate=result.duplicate,
        inbound_email_id=result.inbound_email_id,
    )
