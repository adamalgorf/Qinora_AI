"""Cost-plus-markup pricing for a freshly parsed/updated transport request:
carrier_cost = base_price + price_per_kg * total_weight_kg (from the
matching rate profile), customer_price = carrier_cost * (1 + markup% / 100).

markup% comes from the matched CRM contact's default_markup_percent when
set (ContactRecord.default_markup_percent - a field that already existed in
the schema but was never read anywhere before this), otherwise the
deployment-wide QINORA_DEFAULT_MARKUP_PERCENT setting. compute_customer_price()
below is the one place that math lives - application/carrier_rfq_collector.py
reuses it verbatim once a carrier RFQ batch produces a winning offer.

No matching rate profile used to escalate straight to a human (Control
Tower task). Now it instead automatically RFQs the top eligible carriers in
parallel (application/carrier_rfq.py's targeting + the CarrierRfqRepository/
CarrierRfqOutboundRepository ports) and stops - no quote yet, request status
flips to 'sourcing'. application/carrier_rfq_collector.py picks up the
cheapest reply later (or escalates to a human if the sourcing window elapses
with no reply). Escalating to a human immediately is still exactly what
happens when there's no rate profile AND no eligible/emailed carrier to RFQ
either - there's nothing automatic left to try at that point.
"""

from dataclasses import dataclass

from qinora.application.carrier_rfq import CarrierRfqTargeting, SelectRfqTargetsCommand
from qinora.application.ports import (
    CarrierRfqOutboundRepository,
    CarrierRfqRepository,
    OperationalTaskWriteRepository,
    RateProfileRepository,
    RequestWriteRepository,
)
from qinora.application.quote_workflow import CreateQuoteCommand, QuoteWorkflow, SendQuoteCommand
from qinora.application.read_models import (
    CarrierRfqRecord,
    ContactRecord,
    OutboundReplyRecord,
    QuoteRecord,
)

NO_CARRIERS_REASON = "no rate profile and no carriers available to RFQ"
SOURCING_STATUS = "sourcing"


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
    # Populated instead of quote/outbound_reply when this call kicked off an
    # automatic carrier RFQ batch rather than pricing immediately (see
    # PricingEngine._start_carrier_sourcing, below).
    rfq_batch: tuple[CarrierRfqRecord, ...] = ()


def compute_customer_price(
    carrier_cost: float, contact: ContactRecord | None, default_markup_percent: float
) -> float:
    """The single cost-plus-markup calculation used both for a matched
    rate_profile (PricingEngine.price_and_quote, below) and for a collected
    carrier RFQ offer (application/carrier_rfq_collector.py) - kept here,
    not duplicated, so the two pricing paths can never drift apart.
    """
    markup_percent = (
        contact.default_markup_percent
        if contact is not None and contact.default_markup_percent > 0
        else default_markup_percent
    )
    return round(carrier_cost * (1 + markup_percent / 100), 2)


class PricingEngine:
    def __init__(
        self,
        rate_profiles: RateProfileRepository,
        quote_workflow: QuoteWorkflow,
        task_repository: OperationalTaskWriteRepository,
        default_markup_percent: float,
        carrier_rfq_targeting: CarrierRfqTargeting,
        carrier_rfqs: CarrierRfqRepository,
        carrier_rfq_outbound: CarrierRfqOutboundRepository,
        request_repository: RequestWriteRepository,
    ) -> None:
        self._rate_profiles = rate_profiles
        self._quote_workflow = quote_workflow
        self._task_repository = task_repository
        self._default_markup_percent = default_markup_percent
        self._carrier_rfq_targeting = carrier_rfq_targeting
        self._carrier_rfqs = carrier_rfqs
        self._carrier_rfq_outbound = carrier_rfq_outbound
        self._request_repository = request_repository

    async def price_and_quote(self, command: PriceAndQuoteCommand) -> PricingResult:
        profile = await self._rate_profiles.find_matching(
            mode=command.mode,
            origin=command.origin or None,
            destination=command.destination or None,
        )
        if profile is None:
            return await self._start_carrier_sourcing(command)

        carrier_cost = profile.base_price + profile.price_per_kg * command.total_weight_kg
        customer_price = compute_customer_price(
            carrier_cost, command.contact, self._default_markup_percent
        )

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

    async def _start_carrier_sourcing(self, command: PriceAndQuoteCommand) -> PricingResult:
        targets = await self._carrier_rfq_targeting.select_targets(
            SelectRfqTargetsCommand(mode=command.mode, total_weight_kg=command.total_weight_kg)
        )
        if not targets:
            await self._task_repository.create_task(
                entity_type="transport_request",
                entity_id=command.request_id,
                reason=NO_CARRIERS_REASON,
            )
            return PricingResult(quote=None, outbound_reply=None, priced=False)

        rfqs = await self._carrier_rfqs.create_batch(
            request_id=command.request_id,
            carrier_ids=tuple(carrier.id for carrier in targets),
        )
        carriers_by_id = {carrier.id: carrier for carrier in targets}
        for rfq in rfqs:
            carrier = carriers_by_id.get(rfq.carrier_id)
            if carrier is None or not carrier.email:
                continue
            subject, body_text = _build_rfq_email(rfq, command)
            await self._carrier_rfq_outbound.enqueue(
                carrier_rfq_id=rfq.id,
                recipient=carrier.email,
                subject=subject,
                body_text=body_text,
            )

        await self._request_repository.update_request_status(command.request_id, SOURCING_STATUS)

        return PricingResult(
            quote=None,
            outbound_reply=None,
            priced=False,
            rfq_batch=tuple(rfqs),
        )


def _build_rfq_email(rfq: CarrierRfqRecord, command: PriceAndQuoteCommand) -> tuple[str, str]:
    origin = command.origin or "TBD"
    destination = command.destination or "TBD"
    subject = f"QiNora RFQ #{rfq.correlation_token} - {origin} -> {destination}, {command.mode}"
    body_text = (
        f"Hi,\n\nWe have a {command.mode.upper()} shipment and would like a rate quote:\n\n"
        f"Origin: {origin}\n"
        f"Destination: {destination}\n"
        f"Weight: {command.total_weight_kg:g} kg\n\n"
        "Please reply to this email with your price and transit time - keep this subject "
        "line intact (including the RFQ number) so your reply is matched automatically.\n\n"
        "Thanks,\nQiNora"
    )
    return subject, body_text
