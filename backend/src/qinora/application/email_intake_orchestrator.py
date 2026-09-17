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

import logging
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
from qinora.application.greeting import greeting
from qinora.application.operational_queries import OperationalQueries
from qinora.application.ports import (
    CarrierRfqRepository,
    ClarificationOutboundRepository,
    EmailThreadRepository,
    OperationalTaskWriteRepository,
    QuoteReplyInterpretationLLM,
)
from qinora.application.pricing_engine import PriceAndQuoteCommand, PricingEngine
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
from qinora.application.thread_matching import ThreadMatchingUseCase, ThreadMatchResult
from qinora.domain.shipment_status import ShipmentStatus

log = logging.getLogger("qinora.email_intake_orchestrator")

PARSEK_AGENT_KEY = "request_parsing_agent"

MANUAL_REVIEW_REASON = "granska och svara manuellt"
CRASH_REVIEW_REASON = "automatisk hantering misslyckades - granska manuellt"

# Matches the subject line application/pricing_engine.py's _build_rfq_email
# generates, e.g. "QiNora RFQ #A1B2C3D4 - Stockholm -> Hamburg, ltl" - also
# matches "Re: QiNora RFQ #A1B2C3D4 ..." since it only anchors on the token
# itself, not the start of the string.
RFQ_TOKEN_RE = re.compile(r"QiNora RFQ #([0-9a-fA-F]{8})", re.IGNORECASE)

# Matches the subject line application/quote_workflow.py's send_quote
# generates, e.g. "Din offert - a1b2c3d4-..." - also matches
# "Re: Din offert - a1b2c3d4-..." for the same reason RFQ_TOKEN_RE does.
# Belt-and-suspenders alongside application/thread_matching.py's
# In-Reply-To/References/subject matching: workers/outlook_bridge.py's
# graph.reply() occasionally can't find the original message via Graph's
# internetMessageId search and falls back to sending the quote as a brand
# new email (see its "sending as a new mail" log line), which breaks normal
# thread matching entirely since neither the quote's own Message-ID nor its
# exact subject ever appear in email_inbound. The quote id is already right
# there in the subject, so use it directly rather than depending on mail
# threading working correctly.
QUOTE_ID_RE = re.compile(
    r"Din offert - ([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
    re.IGNORECASE,
)

# Matches the subject line application/carrier_rfq_collector.py's
# _build_offer_report_email generates, e.g. "QiNora Offert #a1b2c3d4-... -
# transportörssvar" - the carrier-facing mailbox (e.g. qinora.ai@) reporting
# the winning carrier rate to the customer-facing mailbox (e.g.
# test.spedition@) once a sourcing batch is done. See
# carrier_rfq_collector.py's module docstring for why this is a real email
# hop between two mailboxes rather than one function finishing the job.
OFFER_REPORT_RE = re.compile(
    r"QiNora Offert #([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
    re.IGNORECASE,
)

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
        quote_reply_llm: QuoteReplyInterpretationLLM,
        carrier_mailbox: str | None = None,
        clarification_outbound: ClarificationOutboundRepository | None = None,
        customer_mailbox: str | None = None,
    ) -> None:
        self._agent_config = agent_config
        self._contact_matching = contact_matching
        self._thread_matching = thread_matching
        self._email_threads = email_threads
        self._operational_queries = operational_queries
        self._booking_workflow = booking_workflow
        self._task_repository = task_repository
        # The carrier-facing mailbox (e.g. qinora.ai@sandahls.com) - lets
        # this (customer-facing) orchestrator instance recognize an inbound
        # offer-report email as coming from its own carrier desk rather than
        # from a customer or an actual carrier. See _match_offer_report()
        # and carrier_rfq_collector.py's module docstring.
        self._carrier_mailbox = carrier_mailbox
        self._request_parsing_agent = request_parsing_agent
        self._pricing_engine = pricing_engine
        self._carrier_rfqs = carrier_rfqs
        self._carrier_offer_agent = carrier_offer_agent
        self._carrier_rfq_collector = carrier_rfq_collector
        self._quote_reply_llm = quote_reply_llm
        # Used only by handle()'s top-level crash safety net, below - lets a
        # customer whose email crashed automated processing still get a
        # reply telling them it's being looked at manually, same as
        # request_parsing_agent.py/pricing_engine.py's holding
        # acknowledgments for their own (non-crash) silent-outcome gaps.
        self._clarification_outbound = clarification_outbound
        self._customer_mailbox = customer_mailbox

    async def handle(self, email_id: str) -> HandleInboundEmailResult:
        """Top-level entry point - see _handle() for the real pipeline.

        Every step below this point is wrapped in one last-resort net: an
        unhandled exception ANYWHERE in the pipeline (a corrupted secret, an
        LLM returning a value outside a closed set, or whatever the next
        unforeseen bug turns out to be - three unrelated examples, all hit
        live in production 2026-09-16/17) crashes this call synchronously.
        By the time that happens, EmailWebhookUseCase.save()/record() has
        already committed, so the email is permanently "already handled"
        for idempotency purposes even though nothing actually replied to
        it - nothing retries it, and the sender is left in silence
        indefinitely. Every individual bug behind today's incidents is
        fixed, but the NEXT unknown one would hit this exact same failure
        mode. Catching it here - log it, escalate it, still try to tell the
        customer - means a future bug degrades to "this one case needs a
        human," not "this one case is silently lost forever."
        """
        try:
            return await self._handle(email_id)
        except Exception as exc:  # noqa: BLE001 - see docstring above
            return await self._handle_crash(email_id, exc)

    async def _handle(self, email_id: str) -> HandleInboundEmailResult:
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

        offer_report_request_id = self._match_offer_report(email)
        if offer_report_request_id is not None:
            return await self._handle_offer_report(email_id, offer_report_request_id)

        match_result = await self._contact_matching.execute(
            MatchContactCommand(sender=email.sender, inbound_email_id=email_id)
        )
        contact = match_result.contact

        thread_match = await self._thread_matching.match(
            email_id=email_id,
            sender=email.sender,
            subject=email.subject,
            message_id=email.message_id,
            in_reply_to=email.in_reply_to,
            references=email.references_header,
        )
        request_id = thread_match.request_id if thread_match else None
        quote_id = thread_match.quote_id if thread_match else None

        if quote_id is None:
            subject_match = await self._match_quote_reply_subject(email.subject)
            if subject_match is not None:
                quote_id, matched_request_id = subject_match
                request_id = request_id or matched_request_id

        if quote_id:
            quote_detail = await self._operational_queries.get_quote_detail(quote_id)
            if quote_detail is not None:
                status = quote_detail.quote.status
                if status in ACTIVE_QUOTE_STATUSES:
                    interpretation = await self._quote_reply_llm.interpret(
                        body_text=email.body_text
                    )
                    intent = interpretation.intent
                    if intent is QuoteReplyIntent.ACCEPTED:
                        await self._book_accepted_quote(
                            quote_id, quote_detail.quote.request_id, recipient_email=email.sender
                        )
                        await self._email_threads.link_thread(
                            email_id, request_id=request_id, quote_id=quote_id
                        )
                        return await self._finish(email_id, "accepted")
                elif status in CLOSED_QUOTE_STATUSES:
                    # Still notify a human (a reply on a finished quote is
                    # worth a look), but don't block on one: the quote is
                    # done (accepted/rejected/expired/converted), so this
                    # reply can't be an edit to it - treat it as a fresh
                    # inquiry instead of reopening something finished.
                    # Clearing request_id/quote_id here (rather than
                    # returning early) means the rest of this method falls
                    # through to Parsek exactly as it would for a genuinely
                    # new email. User's explicit call 2026-09-17: automate
                    # rather than stall on a human for this too.
                    await self._escalate("quote", quote_id)
                    request_id = None
                    quote_id = None

            if quote_id:
                shipment = await self._find_shipment_for_quote(quote_id)
                if shipment is not None and shipment.status in CLOSED_SHIPMENT_STATUSES:
                    await self._escalate("shipment", shipment.id)
                    request_id = None
                    quote_id = None

        if request_id:
            request_detail = await self._operational_queries.get_request_detail(request_id)
            if (
                request_detail is not None
                and request_detail.request.status in CLOSED_REQUEST_STATUSES
            ):
                await self._escalate("transport_request", request_id)
                request_id = None
                quote_id = None

        history = (
            await self._email_threads.list_thread_history(
                request_id=request_id, quote_id=quote_id
            )
            if request_id or quote_id
            else await self._unlinked_thread_history(thread_match, email)
        )
        combined_text = _build_combined_text(history, email)
        customer_name = contact.display_name if contact else email.sender

        result = await self._request_parsing_agent.execute(
            ParseFreeTextRequestCommand(
                customer=customer_name,
                raw_text=combined_text,
                matched_request_id=request_id,
                inbound_email_id=email_id,
                sender_email=email.sender,
                sender_name=email.sender_name,
                subject=email.subject,
                message_id=email.message_id,
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
                inbound_email_id=email_id,
                subject=email.subject,
                sender_name=email.sender_name,
                message_id=email.message_id,
            )
        )
        return await self._finish(email_id, "transport_request")

    async def _unlinked_thread_history(
        self, thread_match: ThreadMatchResult | None, email: InboundEmailRecord
    ) -> list[InboundEmailRecord]:
        """A reply on a thread whose earlier message never became a request
        (e.g. Parsek flagged it for a clarification instead - see
        request_parsing_agent.py's needs_review gate) has no request_id/
        quote_id to look up history by, so list_thread_history returns
        nothing. Fall back to the single anchor email thread_matching
        already resolved, so Parsek still sees the original request details
        (origin/destination/cargo) alongside this reply's answer, instead of
        just the reply text in isolation - which is otherwise low-confidence
        or unparseable on its own.
        """
        if thread_match is None:
            return []
        anchor = await self._email_threads.get(thread_match.matched_email_id)
        if anchor is None or anchor.id == email.id:
            return []
        return [anchor]

    async def _match_quote_reply_subject(self, subject: str) -> tuple[str, str | None] | None:
        match = QUOTE_ID_RE.search(subject)
        if match is None:
            return None
        quote_id = match.group(1)
        quote_detail = await self._operational_queries.get_quote_detail(quote_id)
        if quote_detail is None:
            return None
        return quote_id, quote_detail.quote.request_id

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

    def _match_offer_report(self, email: InboundEmailRecord) -> str | None:
        """True (returns the request_id) when this inbound email is the
        carrier desk's rate report (application/carrier_rfq_collector.py's
        finalize_batch()), not a customer or carrier message - requires both
        the subject token AND the sender being our own configured carrier
        mailbox, so a customer can't spoof this by guessing/quoting the
        subject format.
        """
        if not self._carrier_mailbox:
            return None
        if email.sender.strip().lower() != self._carrier_mailbox.strip().lower():
            return None
        token_match = OFFER_REPORT_RE.search(email.subject)
        return token_match.group(1) if token_match else None

    async def _handle_offer_report(
        self, email_id: str, request_id: str
    ) -> HandleInboundEmailResult:
        await self._email_threads.link_thread(email_id, request_id=request_id, quote_id=None)
        # Mark the classification BEFORE finalizing the customer quote, not
        # after (unlike every other branch here that uses self._finish()) -
        # application/quote_workflow.py's latest_customer_email() (called
        # from inside finalize_customer_quote() to pick who to quote) reads
        # this row's classification from the database, and needs it to
        # already say "carrier_offer_report" so it's excluded from the
        # "customer" candidates. Left at self._finish()'s normal
        # after-the-fact ordering, this row was still whatever the default
        # classification was at insert time and got picked as "the
        # customer" by mistake - its sender is qinora.ai@, not the customer
        # - sending the customer's own quote back to qinora.ai instead.
        # Reproduced live 2026-09-16.
        await self._email_threads.mark_classification(email_id, "carrier_offer_report")
        await self._carrier_rfq_collector.finalize_customer_quote(request_id)
        return HandleInboundEmailResult(classification="carrier_offer_report")

    async def _book_accepted_quote(
        self, quote_id: str, request_id: str | None, *, recipient_email: str
    ) -> None:
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
                recipient_email=recipient_email,
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

    async def _handle_crash(self, email_id: str, exc: Exception) -> HandleInboundEmailResult:
        """handle()'s top-level safety net - see its docstring for why this
        exists. Every step here is individually best-effort (its own
        try/except): a bug in the *recovery* path must never itself
        propagate and defeat the whole point of this being a safety net.
        """
        log.error("Unhandled exception processing email %s", email_id, exc_info=exc)

        try:
            await self._task_repository.create_task(
                entity_type="email_inbound",
                entity_id=email_id,
                priority="high",
                reason=f"{CRASH_REVIEW_REASON} ({type(exc).__name__}: {exc})",
            )
        except Exception:  # noqa: BLE001 - escalating must not itself crash the net
            log.error("Failed to create crash-escalation task for %s", email_id, exc_info=True)

        try:
            await self._email_threads.mark_classification(email_id, "error")
        except Exception:  # noqa: BLE001
            log.error("Failed to mark %s as errored", email_id, exc_info=True)

        try:
            email = await self._email_threads.get(email_id)
        except Exception:  # noqa: BLE001
            email = None

        if email is not None and self._clarification_outbound is not None and email.sender:
            try:
                await self._send_crash_acknowledgment(email)
            except Exception:  # noqa: BLE001
                log.error(
                    "Failed to send crash acknowledgment for %s", email_id, exc_info=True
                )

        return HandleInboundEmailResult(classification="error")

    async def _send_crash_acknowledgment(self, email: InboundEmailRecord) -> None:
        original_subject = email.subject or "din förfrågan"
        subject = original_subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        body_text = (
            f"{greeting(email.sender_name, email.sender)}\n\n"
            f'Tack för ditt mail angående "{original_subject}". Vi har tagit emot det, '
            "men stötte på ett tekniskt problem när vi behandlade det automatiskt. "
            "En av våra medarbetare tittar på det manuellt och återkommer så snart "
            "som möjligt.\n\n"
            "Med vänlig hälsning,\nSandahls"
        )

        assert self._clarification_outbound is not None
        await self._clarification_outbound.enqueue(
            inbound_email_id=email.id,
            recipient=email.sender,
            subject=subject,
            body_text=body_text,
            in_reply_to_message_id=email.message_id,
            sender_mailbox=self._customer_mailbox,
        )


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
