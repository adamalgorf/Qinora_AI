from typing import Protocol

from qinora.application.read_models import (
    AgentLogRecord,
    CarrierRecord,
    InboxRecord,
    QuoteRecord,
    RequestRecord,
    ShipmentRecord,
)


class WebhookEventRepository(Protocol):
    async def exists(self, idempotency_key: str) -> bool:
        pass

    async def record(self, idempotency_key: str, event_type: str) -> None:
        pass


class InboundEmailRepository(Protocol):
    async def save(
        self,
        *,
        idempotency_key: str,
        sender: str,
        subject: str,
        body_text: str,
    ) -> str:
        pass


class AgentDispatcher(Protocol):
    async def dispatch(self, *, event_type: str, entity_id: str) -> None:
        pass


class OperationalReadRepository(Protocol):
    async def list_requests(self) -> list[RequestRecord]:
        pass

    async def list_quotes(self) -> list[QuoteRecord]:
        pass

    async def list_shipments(self) -> list[ShipmentRecord]:
        pass

    async def list_carriers(self) -> list[CarrierRecord]:
        pass

    async def list_inbox(self) -> list[InboxRecord]:
        pass

    async def list_agent_logs(self) -> list[AgentLogRecord]:
        pass
