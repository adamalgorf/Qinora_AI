from typing import Protocol

from qinora.application.read_models import (
    AgentLogRecord,
    CarrierRecord,
    InboxRecord,
    QuoteRecord,
    RequestRecord,
    ShipmentRecord,
)
from qinora.domain import Quote, TransportRequestInput


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


class RequestWriteRepository(Protocol):
    async def create_transport_request(
        self,
        *,
        customer: str,
        lane: str,
        request: TransportRequestInput,
        status: str,
        review_reason: str | None,
    ) -> RequestRecord:
        pass


class QuoteWriteRepository(Protocol):
    async def create_quote(
        self,
        *,
        request_id: str,
        customer_price: float,
        currency: str,
    ) -> QuoteRecord:
        pass

    async def get_quote(self, quote_id: str) -> Quote | None:
        pass

    async def mark_quote_sent(self, quote_id: str) -> QuoteRecord:
        pass

    async def mark_quote_accepted(self, quote_id: str) -> QuoteRecord:
        pass


class ShipmentWriteRepository(Protocol):
    async def create_shipment(
        self,
        *,
        quote_id: str,
        carrier_id: str | None,
        lane: str,
        status: str,
        eta: str,
    ) -> ShipmentRecord:
        pass

    async def update_status(self, shipment_id: str, status: str) -> ShipmentRecord | None:
        pass
