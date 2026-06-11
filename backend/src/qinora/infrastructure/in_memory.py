from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class InMemoryWebhookEventRepository:
    keys: set[str] = field(default_factory=set)

    async def exists(self, idempotency_key: str) -> bool:
        return idempotency_key in self.keys

    async def record(self, idempotency_key: str, event_type: str) -> None:
        _ = event_type
        self.keys.add(idempotency_key)


@dataclass
class InMemoryInboundEmailRepository:
    emails: dict[str, dict[str, str]] = field(default_factory=dict)

    async def save(
        self,
        *,
        idempotency_key: str,
        sender: str,
        subject: str,
        body_text: str,
    ) -> str:
        email_id = str(uuid4())
        self.emails[email_id] = {
            "idempotency_key": idempotency_key,
            "sender": sender,
            "subject": subject,
            "body_text": body_text,
        }
        return email_id


@dataclass
class RecordingAgentDispatcher:
    dispatched: list[tuple[str, str]] = field(default_factory=list)

    async def dispatch(self, *, event_type: str, entity_id: str) -> None:
        self.dispatched.append((event_type, entity_id))
