"""Cost-plus-markup pricing for a freshly parsed/updated transport request:
carrier_cost = base_price + price_per_kg * total_weight_kg (from the
matching rate profile), customer_price = carrier_cost * (1 + markup% / 100).

markup% comes from the matched CRM contact's default_markup_percent when
set (ContactRecord.default_markup_percent - a field that already existed in
the schema but was never read anywhere before this), otherwise the
deployment-wide QINORA_DEFAULT_MARKUP_PERCENT setting.

No matching rate profile is never a silent $0 quote - it escalates to a
human (Control Tower task) and leaves the request in needs_review instead.
"""

from dataclasses import dataclass

from qinora.application.ports import OperationalTaskWriteRepository, RateProfileRepository
from qinora.application.quote_workflow import CreateQuoteCommand, QuoteWorkflow, SendQuoteCommand
from qinora.application.read_models import ContactRecord, OutboundReplyRecord, QuoteRecord


@dataclass(frozen=True)
class PriceAndQuoteCommand:
    request_id: str
    mode: str
    origin: str | None
    destination: str | None
    total_weight_kg: float
    contact: ContactRecord | None
    recipient_email: str


@dataclass(frozen=True)
class PricingResult:
    quote: QuoteRecord | None
    outbound_reply: OutboundReplyRecord | None
    priced: bool


class PricingEngine:
    def __init__(
        self,
        rate_profiles: RateProfileRepository,
        quote_workflow: QuoteWorkflow,
        task_repository: OperationalTaskWriteRepository,
        default_markup_percent: float,
    ) -> None:
        self._rate_profiles = rate_profiles
        self._quote_workflow = quote_workflow
        self._task_repository = task_repository
        self._default_markup_percent = default_markup_percent

    async def price_and_quote(self, command: PriceAndQuoteCommand) -> PricingResult:
        profile = await self._rate_profiles.find_matching(
            mode=command.mode,
            origin=command.origin or None,
            destination=command.destination or None,
        )
        if profile is None:
            await self._task_repository.create_task(
                entity_type="transport_request",
                entity_id=command.request_id,
                reason="needs pricing",
            )
            return PricingResult(quote=None, outbound_reply=None, priced=False)

        carrier_cost = profile.base_price + profile.price_per_kg * command.total_weight_kg
        markup_percent = (
            command.contact.default_markup_percent
            if command.contact is not None and command.contact.default_markup_percent > 0
            else self._default_markup_percent
        )
        customer_price = round(carrier_cost * (1 + markup_percent / 100), 2)

        quote = await self._quote_workflow.create_quote(
            CreateQuoteCommand(
                request_id=command.request_id,
                customer_price=customer_price,
                currency=profile.currency,
            )
        )
        send_result = await self._quote_workflow.send_quote(
            SendQuoteCommand(quote_id=quote.id, recipient=command.recipient_email)
        )
        return PricingResult(
            quote=send_result.quote,
            outbound_reply=send_result.outbound_reply,
            priced=True,
        )
