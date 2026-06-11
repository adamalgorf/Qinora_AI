from dataclasses import dataclass

from qinora.application.ports import (
    AgentDispatcher,
    InboundEmailRepository,
    WebhookEventRepository,
)


@dataclass(frozen=True)
class EmailWebhookCommand:
    idempotency_key: str
    sender: str
    subject: str
    body_text: str


@dataclass(frozen=True)
class EmailWebhookResult:
    accepted: bool
    inbound_email_id: str | None
    duplicate: bool = False


class EmailWebhookUseCase:
    def __init__(
        self,
        webhook_events: WebhookEventRepository,
        inbound_emails: InboundEmailRepository,
        dispatcher: AgentDispatcher,
    ) -> None:
        self._webhook_events = webhook_events
        self._inbound_emails = inbound_emails
        self._dispatcher = dispatcher

    async def execute(self, command: EmailWebhookCommand) -> EmailWebhookResult:
        if await self._webhook_events.exists(command.idempotency_key):
            return EmailWebhookResult(accepted=True, inbound_email_id=None, duplicate=True)

        inbound_email_id = await self._inbound_emails.save(
            idempotency_key=command.idempotency_key,
            sender=command.sender,
            subject=command.subject,
            body_text=command.body_text,
        )
        await self._webhook_events.record(command.idempotency_key, "email.received")
        await self._dispatcher.dispatch(event_type="email.received", entity_id=inbound_email_id)

        return EmailWebhookResult(accepted=True, inbound_email_id=inbound_email_id)
