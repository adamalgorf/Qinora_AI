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
    recipient: str = ""
    message_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    sender_name: str | None = None


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
            recipient=command.recipient,
            message_id=command.message_id,
            in_reply_to=command.in_reply_to,
            references_header=command.references,
            sender_name=command.sender_name,
        )
        await self._webhook_events.record(command.idempotency_key, "email.received")
        # The real AgentDispatcher (infrastructure/email_dispatch.py) runs
        # the full intake pipeline synchronously here, including contact
        # matching - see application/email_intake_orchestrator.py. Tests
        # that don't care about the pipeline use RecordingAgentDispatcher
        # (infrastructure/in_memory.py) instead.
        await self._dispatcher.dispatch(event_type="email.received", entity_id=inbound_email_id)

        return EmailWebhookResult(accepted=True, inbound_email_id=inbound_email_id)
