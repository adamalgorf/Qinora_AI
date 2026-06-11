from dataclasses import dataclass

from qinora.application.ports import QuoteWriteRepository
from qinora.application.read_models import QuoteRecord
from qinora.domain import can_send_quote


@dataclass(frozen=True)
class CreateQuoteCommand:
    request_id: str
    customer_price: float
    currency: str = "SEK"


@dataclass(frozen=True)
class SendQuoteCommand:
    quote_id: str


class QuoteWorkflow:
    def __init__(self, repository: QuoteWriteRepository) -> None:
        self._repository = repository

    async def create_quote(self, command: CreateQuoteCommand) -> QuoteRecord:
        return await self._repository.create_quote(
            request_id=command.request_id,
            customer_price=command.customer_price,
            currency=command.currency,
        )

    async def send_quote(self, command: SendQuoteCommand) -> QuoteRecord:
        quote = await self._repository.get_quote(command.quote_id)

        if quote is None:
            raise QuoteNotFoundError(command.quote_id)

        allowed, reason = can_send_quote(quote)
        if not allowed:
            raise PricingGateError(reason or "Quote cannot be sent")

        return await self._repository.mark_quote_sent(command.quote_id)


class QuoteNotFoundError(LookupError):
    pass


class PricingGateError(ValueError):
    pass
