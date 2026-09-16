"""Finalizes an automatic carrier RFQ batch (application/pricing_engine.py's
carrier-sourcing branch) once it's ready: either every RFQ in the batch has
a reply, or the sourcing window has elapsed. Mirrors the
application/stale_request_escalation.py / workers/stale_request_escalator.py
pattern - the same "cutoff = now - window, sweep for candidates, escalate/act"
shape - but with two entry points instead of one:

  - run() - a periodic sweep (invoked from workers/carrier_rfq_collector.py,
    or from the /outbound/collect-carrier-rfqs endpoint - see
    interfaces/http/routers/outbound.py) that expires any RFQ whose sourcing
    window has elapsed and finalizes the batches that touches.
  - finalize_batch() - called immediately by
    application/email_intake_orchestrator.py the moment the last outstanding
    RFQ in a batch gets a reply, so a fully-responded batch doesn't have to
    wait for the next sweep. run() also delegates to this for the batches it
    touches, so the "pick cheapest, price it" logic only lives in one place.

Picking the cheapest offer and actually quoting the customer are two
separate steps, deliberately not one: once the batch is ready,
finalize_batch() picks the winner and reports it to the customer-facing
mailbox (e.g. test.spedition@sandahls.com) as a real email from the
carrier-facing mailbox (e.g. qinora.ai@sandahls.com) - see
CarrierOfferReportOutboundRecord's docstring. Only once THAT email lands
back in the customer mailbox's inbox does
application/email_intake_orchestrator.py's offer-report detection call
finalize_customer_quote() below to actually price and send the customer
quote. This mirrors how a real freight desk works - someone checks rates
and reports the number to the person who owns the customer relationship,
who then quotes the customer - and keeps that handoff visible as an actual
email in the case's conversation instead of a silent internal function
call. Confirmed as the required behavior 2026-09-16 after the internal-only
version shipped: it computed and sent the customer quote directly, with no
mailbox-to-mailbox email in between.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from qinora.application.ports import (
    CarrierOfferReportOutboundRepository,
    CarrierOfferWriteRepository,
    CarrierRfqRepository,
    ContactReadRepository,
    EmailThreadRepository,
    OperationalTaskWriteRepository,
    RequestWriteRepository,
)
from qinora.application.pricing_engine import compute_customer_price
from qinora.application.quote_workflow import (
    CreateQuoteCommand,
    QuoteWorkflow,
    SendQuoteCommand,
    first_customer_email,
)
from qinora.application.read_models import CarrierOfferRecord, QuoteRecord

NO_RESPONSE_REASON = "no carrier response, needs manual sourcing"
NO_RECIPIENT_REASON = "cheapest carrier offer collected but no customer email on file to quote"
NO_REPORT_ROUTE_REASON = (
    "cheapest carrier offer collected but no carrier/customer mailbox configured to report it"
)
QUOTED_STATUS = "quoted"

DEFAULT_WINDOW_HOURS = 24


@dataclass(frozen=True)
class CollectCarrierRfqsCommand:
    window_hours: int = DEFAULT_WINDOW_HOURS


@dataclass(frozen=True)
class FinalizedBatch:
    request_id: str
    quote: QuoteRecord | None
    escalated: bool


@dataclass(frozen=True)
class CollectCarrierRfqsResult:
    finalized: tuple[FinalizedBatch, ...]


class CarrierRfqCollector:
    def __init__(
        self,
        carrier_rfqs: CarrierRfqRepository,
        carrier_offers: CarrierOfferWriteRepository,
        email_threads: EmailThreadRepository,
        contacts: ContactReadRepository,
        quote_workflow: QuoteWorkflow,
        task_repository: OperationalTaskWriteRepository,
        request_repository: RequestWriteRepository,
        default_markup_percent: float,
        carrier_offer_report_outbound: CarrierOfferReportOutboundRepository | None = None,
        carrier_mailbox: str | None = None,
        customer_mailbox: str | None = None,
    ) -> None:
        self._carrier_rfqs = carrier_rfqs
        self._carrier_offers = carrier_offers
        self._email_threads = email_threads
        self._contacts = contacts
        self._quote_workflow = quote_workflow
        self._task_repository = task_repository
        self._request_repository = request_repository
        self._default_markup_percent = default_markup_percent
        self._carrier_offer_report_outbound = carrier_offer_report_outbound
        # Which mailbox reports the winning carrier rate (e.g.
        # qinora.ai@sandahls.com) and which mailbox receives that report and
        # owns the customer relationship (e.g. test.spedition@sandahls.com).
        # Both unset means single-mailbox deployments - see
        # finalize_batch()'s fallback below.
        self._carrier_mailbox = carrier_mailbox
        self._customer_mailbox = customer_mailbox

    async def run(self, command: CollectCarrierRfqsCommand) -> CollectCarrierRfqsResult:
        cutoff = datetime.now(UTC) - timedelta(hours=command.window_hours)
        newly_expired = await self._carrier_rfqs.expire_stale(cutoff.isoformat(timespec="seconds"))
        # dict.fromkeys instead of a set - preserves a stable, deterministic
        # order for tests/logging without needing a second sort.
        request_ids = dict.fromkeys(rfq.request_id for rfq in newly_expired)

        finalized: list[FinalizedBatch] = []
        for request_id in request_ids:
            outcome = await self.finalize_batch(request_id)
            if outcome is not None:
                finalized.append(outcome)

        return CollectCarrierRfqsResult(finalized=tuple(finalized))

    async def finalize_batch(self, request_id: str) -> FinalizedBatch | None:
        """Finalizes request_id's carrier RFQ batch if every RFQ in it has
        left the 'sent' state (i.e. each has either responded or expired).
        Returns None if the batch doesn't exist or is still waiting on a
        reply - callers (run(), above, and
        application/email_intake_orchestrator.py) only invoke this once
        they already believe the batch is ready, but this re-checks rather
        than trusting the caller.

        Picks the cheapest offer and reports it to the customer mailbox by
        email (see module docstring) rather than quoting the customer
        directly - application/email_intake_orchestrator.py's offer-report
        detection calls finalize_customer_quote() below once that report
        email arrives, which is what actually creates and sends the
        customer quote.
        """
        batch = await self._carrier_rfqs.list_batch(request_id)
        if not batch or any(rfq.status == "sent" for rfq in batch):
            return None

        responded = {rfq.id: rfq for rfq in batch if rfq.status == "responded"}
        offers = (
            await self._carrier_offers.list_offers_for_request(request_id) if responded else []
        )
        priced_offers = [
            offer
            for offer in offers
            if offer.carrier_rfq_id in responded and offer.price is not None
        ]

        if not priced_offers:
            await self._task_repository.create_task(
                entity_type="transport_request",
                entity_id=request_id,
                priority="high",
                reason=NO_RESPONSE_REASON,
            )
            return FinalizedBatch(request_id=request_id, quote=None, escalated=True)

        cheapest = min(priced_offers, key=lambda offer: offer.price)

        losing_ids = tuple(
            rfq.id
            for rfq in batch
            if rfq.status == "responded" and rfq.id != cheapest.carrier_rfq_id
        )
        if losing_ids:
            await self._carrier_rfqs.mark_superseded(losing_ids)

        if self._carrier_offer_report_outbound is None or not self._customer_mailbox:
            # Single-mailbox deployment (no carrier/customer mailbox split
            # configured) - fall back to quoting the customer directly, the
            # only option available without a second mailbox to report to.
            return await self._quote_customer(request_id, cheapest)

        subject, body_text = _build_offer_report_email(request_id, cheapest)
        await self._carrier_offer_report_outbound.enqueue(
            request_id=request_id,
            recipient=self._customer_mailbox,
            subject=subject,
            body_text=body_text,
            sender_mailbox=self._carrier_mailbox,
        )
        return FinalizedBatch(request_id=request_id, quote=None, escalated=False)

    async def finalize_customer_quote(self, request_id: str) -> FinalizedBatch | None:
        """Prices and sends the customer quote for request_id's already-
        decided winning carrier offer - the second half of finalize_batch()
        above, triggered by application/email_intake_orchestrator.py once
        the carrier-offer-report email it sent actually arrives back in the
        customer mailbox. Returns None if there's no winning offer on file
        (the report email arrived for a request that was never actually
        finalized, or was already quoted).
        """
        winning_rfq = await self._carrier_rfqs.find_winning(request_id)
        if winning_rfq is None:
            return None

        offers = await self._carrier_offers.list_offers_for_request(request_id)
        cheapest = next(
            (offer for offer in offers if offer.carrier_rfq_id == winning_rfq.id),
            None,
        )
        if cheapest is None or cheapest.price is None:
            return None

        return await self._quote_customer(request_id, cheapest)

    async def _quote_customer(
        self, request_id: str, cheapest: CarrierOfferRecord
    ) -> FinalizedBatch:
        history = await self._email_threads.list_thread_history(
            request_id=request_id, quote_id=None
        )
        anchor = first_customer_email(history)
        recipient_email = anchor.sender if anchor else None
        if recipient_email is None:
            await self._task_repository.create_task(
                entity_type="transport_request",
                entity_id=request_id,
                priority="high",
                reason=NO_RECIPIENT_REASON,
            )
            return FinalizedBatch(request_id=request_id, quote=None, escalated=True)

        contact = await self._contacts.find_by_sender(recipient_email)
        customer_price = compute_customer_price(
            cheapest.price or 0.0, contact, self._default_markup_percent
        )

        quote = await self._quote_workflow.create_quote(
            CreateQuoteCommand(
                request_id=request_id,
                customer_price=customer_price,
                currency=cheapest.currency or "SEK",
            )
        )
        # Back-fill quote_id onto the request's existing email thread so a
        # later customer reply (accept/reject/revise) can resolve back to
        # this quote via thread_matching - see EmailThreadRepository
        # .link_quote_to_request's docstring for why this is needed here
        # specifically (the quote didn't exist yet when the original request
        # email was linked).
        await self._email_threads.link_quote_to_request(request_id, quote.id)
        send_result = await self._quote_workflow.send_quote(
            SendQuoteCommand(quote_id=quote.id, recipient=recipient_email)
        )
        await self._request_repository.update_request_status(request_id, QUOTED_STATUS)

        return FinalizedBatch(request_id=request_id, quote=send_result.quote, escalated=False)


def _build_offer_report_email(
    request_id: str, cheapest: CarrierOfferRecord
) -> tuple[str, str]:
    subject = f"QiNora Offert #{request_id} - transportörssvar"
    body_text = (
        "Hej,\n\n"
        f"Billigaste transportörssvaret for förfrågan {request_id}:\n\n"
        f"Transportör: {cheapest.carrier_name}\n"
        f"Pris: {cheapest.price:g} {cheapest.currency or 'SEK'}\n"
        + (f"Transittid: {cheapest.transit_days} dagar\n" if cheapest.transit_days else "")
        + "\nVänligen skicka offert till kund.\n\n"
        "Med vänlig hälsning,\nQinora"
    )
    return subject, body_text
