"""Wires an inbound email (already saved to email_inbound by
EmailWebhookUseCase) through the full automated intake pipeline:

  1. Loop-guard - drop our own mail bouncing back to us.
  2. Tenant resolution - a safety/quality gate, see application/email_routing.py.
  3. Carrier RFQ reply routing - a reply carrying a live RFQ correlation
     token (or from a carrier's registered email with an open RFQ) is a
     carrier's rate quote, not a customer email - handed to Remy Rates
     (application/carrier_offer_agent.py) and never reaches the steps below.
     See application/pricing_engine.py / application/carrier_rfq_collector.py
     for where the RFQ itself came from.
  4. Contact matching - who is this, if anyone we know (ContactMatchingUseCase).
  5. Thread matching - which prior request/quote (if any) this continues.
  6. Acceptance shortcut - a deterministic "accept" reply on an open quote
     books the shipment directly, no LLM call.
  7. Closed-thread gate - a reply on an already-closed quote/request/shipment
     is never auto-processed, only escalated for a human to handle.
  8. Otherwise, hand the full thread history to Parsek (extended with a
     classify + create/update/not_relevant step - see
     application/request_parsing_agent.py) and, for a complete request,
     price it and queue the quote (application/pricing_engine.py).

This is the real AgentDispatcher behind the "email.received" event - see
infrastructure/email_dispatch.py for the adapter that invokes `handle()`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from qinora.application.agent_config import AgentConfigService
from qinora.application.booking_workflow import BookingWorkflow, BookQuoteCommand
from qinora.application.carrier_offer_agent import (
    CarrierOfferParsingAgent,
    ParseCarrierOfferCommand,
)
from qinora.application.carrier_rfq_collector import CarrierRfqCollector
from qinora.application.contact_matching import ContactMatchingUseCase, MatchContactCommand
from qinora.application.email_routing import is_loop, resolve_tenant
from qinora.application.operational_queries import OperationalQueries
from qinora.application.ports import (
    CarrierRfqRepository,
    EmailThreadRepository,
    OperationalTaskWriteRepository,
)
from qinora.application.pricing_engine import PriceAndQuoteCommand, PricingEngine
from qinora.application.quote_response_workflow import interpret_quote_reply
from qinora.application.read_models import (
    CarrierRfqRecord,
    InboundEmailRecord,
    QuoteReplyIntent,
    ShipmentRecord,
)
from qinora.application.request_parsing_agent import (
    ParseFreeTextRequestCommand,
    RequestParsingAgent,
)
from qinora.application.thread_matching import ThreadMatchingUseCase
from qinora.domain.shipment_status import ShipmentStatus

PARSEK_AGENT_KEY = "request_parsing_agent"

MANUAL_REVIEW_REASON = "granska och svara manuellt"

# Matches the subject line application/pricing_engine.py's _build_rfq_email
# generates, e.g. "QiNora RFQ #A1B2C3D4 - Stockholm -> Hamburg, ltl" - also
# matches "Re: QiNora RFQ #A1B2C3D4 ..." since it only anchors on the token
# itself, not the start of the string.
RFQ_TOKEN_RE = re.compile(r"QiNora RFQ #([0-9a-fA-F]{8})", re.IGNORECASE)

# An RFQ is still awaiting a reply in this status - see
# application/ports.py's CarrierRfqRepository and migrations/0006_carrier_rfq.sql.
OPEN_RFQ_STATUS = "sent"

# Quote statuses a customer can still meaningfully reply to (accept/revise/reject).
ACTIVE_QUOTE_STATUSES = frozenset({"sent", "viewed"})
# Quote statuses where the thread is done - no further automated action.
CLOSED_QUOTE_STATUSES = frozenset({"accepted", "rejected", "expired", "converted"})
# Request statuses where the thread is done (mirrors OperationalQueries.dashboard_summary's
# existing "converted" convention).
CLOSED_REQUEST_STATUSES = frozenset({"converted"})
CLOSED_SHIPMENT_STATUSES = frozenset(
    {
        ShipmentStatus.INVOICE_APPROVED.value,
        ShipmentStatus.INVOICE_DISPUTED.value,
        ShipmentStatus.CANCELLED.value,
    }
)


@dataclass(frozen=True)
class HandleInboundEmailResult:
    classification: str


class EmailIntakeOrchestrator:
    def __init__(
        self,
        agent_config: AgentConfigService,
        contact_matching: ContactMatchingUseCase,
        thread_matching: ThreadMatchingUseCase,
        email_threads: EmailThreadRepository,
        operational_queries: OperationalQueries,
        booking_workflow: BookingWorkflow,
        task_repository: OperationalTaskWriteRepository,
        request_parsing_agent: RequestParsingAgent,
        pricing_engine: PricingEngine,
        carrier_rfqs: CarrierRfqRepository,
        carrier_offer_agent: CarrierOfferParsingAgent,
        carrier_rfq_collector: CarrierRfqCollector,
    ) -> None:
        self._agent_config = agent_config
        self._contact_matching = contact_matching
        self._thread_matching = thread_matching
        self._email_threads = email_threads
        self._operational_queries = operational_queries
        self._booking_workflow = booking_workflow
        self._task_repository = task_repository
        self._request_parsing_agent = request_parsing_agent
        self._pricing_engine = pricing_engine
        self._carrier_rfqs = carrier_rfqs
        self._carrier_offer_agent = carrier_offer_agent
        self._carrier_rfq_collector = carrier_rfq_collector

    async def handle(self, email_id: str) -> HandleInboundEmailResult:
        email = await self._email_threads.get(email_id)
        if email is None:
            return HandleInboundEmailResult(classification="unknown")

        parsek_config = await self._agent_config.get_config(PARSEK_AGENT_KEY)

        if is_loop(sender=email.sender, parsek_config=parsek_config):
            return await self._finish(email_id, "rejected")

        tenant_id = resolve_tenant(
            sender=email.sender, recipient=email.recipient, parsek_config=parsek_config
        )
        if tenant_id is None:
            return await self._finish(email_id, "rejected")

        carrier_rfq_match = await self._match_carrier_rfq(email)
        if carrier_rfq_match is not None:
            return await self._handle_carrier_reply(email_id, email, carrier_rfq_match)

        match_result = await self._contact_matching.execute(
            MatchContactCommand(sender=email.sender, inbound_email_id=email_id)
        )
        contact = match_result.contact

        thread_match = await self._thread_matching.match(
            sender=email.sender,
            subject=email.subject,
            message_id=email.message_id,
            in_reply_to=email.in_reply_to,
            references=email.references_header,
        )
        request_id = thread_match.request_id if thread_match else None
        quote_id = thread_match.quote_id if thread_match else None

        if quote_id:
            quote_detail = await self._operational_queries.get_quote_detail(quote_id)
            if quote_detail is not None:
                status = quote_detail.quote.status
                if status in ACTIVE_QUOTE_STATUSES:
                    intent = interpret_quote_reply(email.body_text)
                    if intent is QuoteReplyIntent.ACCEPTED:
                        await self._book_accepted_quote(quote_id, quote_detail.quote.request_id)
                        await self._email_threads.link_thread(
                            email_id, request_id=request_id, quote_id=quote_id
                        )
                        return await self._finish(email_id, "accepted")
                elif status in CLOSED_QUOTE_STATUSES:
                    await self._escalate("quote", quote_id)
                    await self._email_threads.link_thread(
                        email_id, request_id=request_id, quote_id=quote_id
                    )
                    return await self._finish(email_id, "closed_thread")

            shipment = await self._find_shipment_for_quote(quote_id)
            if shipment is not None and shipment.status in CLOSED_SHIPMENT_STATUSES:
                await self._escalate("shipment", shipment.id)
                await self._email_threads.link_thread(
                    email_id, request_id=request_id, quote_id=quote_id
                )
                return await self._finish(email_id, "closed_thread")

        if request_id:
            request_detail = await self._operational_queries.get_request_detail(request_id)
            if (
                request_detail is not None
                and request_detail.request.status in CLOSED_REQUEST_STATUSES
            ):
                await self._escalate("transport_request", request_id)
                await self._email_threads.link_thread(
                    email_id, request_id=request_id, quote_id=quote_id
                )
                return await self._finish(email_id, "closed_thread")

        history = (
            await self._email_threads.list_thread_history(
                request_id=request_id, quote_id=quote_id
            )
            if request_id or quote_id
            else []
        )
        combined_text = _build_combined_text(history, email)
        customer_name = contact.display_name if contact else email.sender

        result = await self._request_parsing_agent.execute(
            ParseFreeTextRequestCommand(
                customer=customer_name,
                raw_text=combined_text,
                matched_request_id=request_id,
                inbound_email_id=email_id,
            )
        )

        if result.not_relevant:
            return await self._finish(email_id, "not_relevant")

        if result.request_result is None:
            return await self._finish(email_id, "pending")

        resolved_request_id = result.request_result.request.id
        await self._email_threads.link_thread(
            email_id, request_id=resolved_request_id, quote_id=None
        )

        if not result.request_result.complete:
            # CreateRequestUseCase/UpdateRequestUseCase already opened a
            # Control Tower task for the missing fields.
            return await self._finish(email_id, "transport_request")

        await self._pricing_engine.price_and_quote(
            PriceAndQuoteCommand(
                request_id=resolved_request_id,
                mode=result.draft.mode,
                origin=result.draft.origin,
                destination=result.draft.destination,
                total_weight_kg=result.request_result.request.weight_kg,
                contact=contact,
                recipient_email=email.sender,
            )
        )
        return await self._finish(email_id, "transport_request")

    async def _match_carrier_rfq(self, email: InboundEmailRecord) -> CarrierRfqRecord | None:
        token_match = RFQ_TOKEN_RE.search(email.subject)
        if token_match:
            rfq = await self._carrier_rfqs.find_by_token(token_match.group(1))
            if rfq is not None and rfq.status == OPEN_RFQ_STATUS:
                return rfq
        return await self._carrier_rfqs.find_by_carrier_email(email.sender)

    async def _handle_carrier_reply(
        self, email_id: str, email: InboundEmailRecord, rfq: CarrierRfqRecord
    ) -> HandleInboundEmailResult:
        result = await self._carrier_offer_agent.execute(
            ParseCarrierOfferCommand(request_id=rfq.request_id, raw_text=email.body_text)
        )
        if result.offer is not None:
            await self._carrier_rfqs.mark_responded(rfq.id, result.offer.id)
            still_open = await self._carrier_rfqs.list_open_batch(rfq.request_id)
            if not still_open:
                await self._carrier_rfq_collector.finalize_batch(rfq.request_id)

        await self._email_threads.link_thread(email_id, request_id=rfq.request_id, quote_id=None)
        return await self._finish(email_id, "carrier_offer")

    async def _book_accepted_quote(self, quote_id: str, request_id: str | None) -> None:
        mode = "ltl"
        total_weight_kg = 0.0
        if request_id:
            request_detail = await self._operational_queries.get_request_detail(request_id)
            if request_detail is not None:
                mode = request_detail.request.mode
                total_weight_kg = request_detail.request.weight_kg

        await self._booking_workflow.book_quote(
            BookQuoteCommand(
                quote_id=quote_id,
                mode=mode,
                total_weight_kg=total_weight_kg,
            )
        )

    async def _find_shipment_for_quote(self, quote_id: str) -> ShipmentRecord | None:
        shipments = await self._operational_queries.list_shipments()
        return next((shipment for shipment in shipments if shipment.quote_id == quote_id), None)

    async def _escalate(self, entity_type: str, entity_id: str) -> None:
        await self._task_repository.create_task(
            entity_type=entity_type,
            entity_id=entity_id,
            reason=MANUAL_REVIEW_REASON,
        )

    async def _finish(self, email_id: str, classification: str) -> HandleInboundEmailResult:
        await self._email_threads.mark_classification(email_id, classification)
        return HandleInboundEmailResult(classification=classification)


def _build_combined_text(history: list[InboundEmailRecord], email: InboundEmailRecord) -> str:
    prior = [row for row in history if row.id != email.id]
    if not prior:
        return email.body_text

    segments = [
        f"--- Message from {row.sender} ({row.created_at}) ---\n{row.body_text}" for row in prior
    ]
    segments.append(
        f"--- Message from {email.sender} ({email.created_at}) ---\n{email.body_text}"
    )
    return "\n\n".join(segments)
