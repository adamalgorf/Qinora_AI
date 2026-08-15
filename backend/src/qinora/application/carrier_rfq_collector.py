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
    touches, so the "pick cheapest, price it, mark the rest superseded"
    logic only lives in one place.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from qinora.application.ports import (
    CarrierOfferWriteRepository,
    CarrierRfqRepository,
    ContactReadRepository,
    EmailThreadRepository,
    OperationalTaskWriteRepository,
    RequestWriteRepository,
)
from qinora.application.pricing_engine import compute_customer_price
from qinora.application.quote_workflow import CreateQuoteCommand, QuoteWorkflow, SendQuoteCommand
from qinora.application.read_models import QuoteRecord

NO_RESPONSE_REASON = "no carrier response, needs manual sourcing"
NO_RECIPIENT_REASON = "cheapest carrier offer collected but no customer email on file to quote"
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
    ) -> None:
        self._carrier_rfqs = carrier_rfqs
        self._carrier_offers = carrier_offers
        self._email_threads = email_threads
        self._contacts = contacts
        self._quote_workflow = quote_workflow
        self._task_repository = task_repository
        self._request_repository = request_repository
        self._default_markup_percent = default_markup_percent

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

        history = await self._email_threads.list_thread_history(
            request_id=request_id, quote_id=None
        )
        recipient_email = history[0].sender if history else None
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
        send_result = await self._quote_workflow.send_quote(
            SendQuoteCommand(quote_id=quote.id, recipient=recipient_email)
        )
        await self._request_repository.update_request_status(request_id, QUOTED_STATUS)

        losing_ids = tuple(
            rfq.id
            for rfq in batch
            if rfq.status == "responded" and rfq.id != cheapest.carrier_rfq_id
        )
        if losing_ids:
            await self._carrier_rfqs.mark_superseded(losing_ids)

        return FinalizedBatch(request_id=request_id, quote=send_result.quote, escalated=False)
