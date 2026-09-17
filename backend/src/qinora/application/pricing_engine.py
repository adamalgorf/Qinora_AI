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
from qinora.application.greeting import greeting
from qinora.application.ports import (
    CarrierRfqOutboundRepository,
    CarrierRfqRepository,
    ClarificationOutboundRepository,
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
    # Only needed for the no-rate-profile/no-carriers escalation path below
    # to send the customer a holding acknowledgment instead of silence -
    # None/empty is fine everywhere else.
    inbound_email_id: str | None = None
    subject: str = ""
    sender_name: str | None = None
    message_id: str | None = None


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
        carrier_mailbox: str | None = None,
        clarification_outbound: ClarificationOutboundRepository | None = None,
        customer_mailbox: str | None = None,
    ) -> None:
        self._rate_profiles = rate_profiles
        self._quote_workflow = quote_workflow
        self._task_repository = task_repository
        self._default_markup_percent = default_markup_percent
        self._carrier_rfq_targeting = carrier_rfq_targeting
        self._carrier_rfqs = carrier_rfqs
        self._carrier_rfq_outbound = carrier_rfq_outbound
        self._request_repository = request_repository
        # Which mailbox carrier RFQs should be sent from (e.g.
        # qinora.ai@sandahls.com) when more than one Outlook bridge instance
        # is running - see workers/outlook_bridge.py. None means "any
        # bridge instance may send it" (single-mailbox deployments).
        self._carrier_mailbox = carrier_mailbox
        # Sends the customer a holding acknowledgment when there's no rate
        # profile AND no carrier to RFQ either - see _start_carrier_sourcing
        # below. None disables it (falls back to the old silent-escalation
        # behavior, e.g. in tests that don't care about it).
        self._clarification_outbound = clarification_outbound
        self._customer_mailbox = customer_mailbox

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
            # The request was understood fine - there's just nothing left
            # to price it against automatically. Without this, the customer
            # got total silence even though their request was successfully
            # parsed and created, only surfacing internally as a Control
            # Tower task - every inbound email must get SOME reply.
            # Reproduced live 2026-09-17.
            if (
                self._clarification_outbound is not None
                and command.inbound_email_id
                and command.recipient_email
            ):
                await self._send_no_carrier_acknowledgment(command)
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
                sender_mailbox=self._carrier_mailbox,
            )

        await self._request_repository.update_request_status(command.request_id, SOURCING_STATUS)

        return PricingResult(
            quote=None,
            outbound_reply=None,
            priced=False,
            rfq_batch=tuple(rfqs),
        )

    async def _send_no_carrier_acknowledgment(self, command: PriceAndQuoteCommand) -> None:
        original_subject = command.subject or "din förfrågan"
        subject = original_subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        body_text = (
            f"{greeting(command.sender_name, command.recipient_email)}\n\n"
            f'Tack för din förfrågan angående "{original_subject}". Vi har tagit emot '
            "den och återkommer med en offert så snart som möjligt.\n\n"
            "Med vänlig hälsning,\nSandahls"
        )

        assert self._clarification_outbound is not None
        assert command.inbound_email_id is not None
        await self._clarification_outbound.enqueue(
            inbound_email_id=command.inbound_email_id,
            recipient=command.recipient_email,
            subject=subject,
            body_text=body_text,
            in_reply_to_message_id=command.message_id,
            sender_mailbox=self._customer_mailbox,
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
        "Med vänlig hälsning,\nSandahls"
    )
    return subject, body_text
