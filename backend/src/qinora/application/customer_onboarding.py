"""Onboarding of a new customer when they confirm an order (Nora).

A sender who confirms a quote but isn't a known customer (no contact matches
their address or domain - see application/contact_matching.py) gets an email
asking for their company details: company name, organisation number, contact
person (name, e-mail, phone) and address. Their reply is read here, and once
everything is in, the customer is registered in the customer register - so
the next email from them is matched to a real customer.

Stateless on purpose: there is no "waiting for details" table. A reply on an
already-accepted quote from a sender who is still not a customer is the
trigger (application/email_intake_orchestrator.py); everything the sender has
written since the acceptance is re-read each time, so a partial answer just
gets a follow-up listing what's still missing, and the answer to that
completes the picture.

Booking is never held up by any of this - the shipment is already booked when
we ask (application/booking_workflow.py); a customer who never answers just
stays unregistered, and a human can see that from the thread.
"""

from __future__ import annotations

from dataclasses import dataclass

from qinora.application.agent_config import AgentConfigService, should_auto_act
from qinora.application.customer_import import (
    CustomerImportService,
    CustomerInput,
    CustomerValidationError,
    DuplicateCustomerError,
)
from qinora.application.greeting import greeting
from qinora.application.ports import (
    AgentLogWriteRepository,
    ClarificationOutboundRepository,
    CustomerDetailsParsingLLM,
    OperationalTaskWriteRepository,
)
from qinora.application.read_models import (
    ContactRecord,
    InboundEmailRecord,
    ParsedCustomerDetails,
)

AGENT_KEY = "customer_onboarding_agent"
AGENT_NAME = "Nora"
# Nora's own agent config (auto_mode / min_confidence) governs whether a
# parsed reply is trusted enough to register a customer without a human.
NORA_CONFIG_KEY = "request_parsing_agent"

ACCEPTED_CLASSIFICATION = "accepted"

# (field on ParsedCustomerDetails, label shown to the customer) - in the
# order they're asked for. All of them are required to register the customer.
REQUIRED_DETAILS: tuple[tuple[str, str], ...] = (
    ("company_name", "Företagsnamn"),
    ("org_number", "Organisationsnummer"),
    ("contact_person", "Kontaktperson (namn)"),
    ("contact_email", "Kontaktpersonens e-postadress"),
    ("contact_phone", "Kontaktpersonens telefonnummer"),
    ("address", "Företagets adress (gata, postnummer och ort)"),
)

REVIEW_LOW_CONFIDENCE = "granska kunduppgifter - svaret var svårtolkat, kund ej registrerad"
REVIEW_DUPLICATE = "kunden finns redan - koppla avsändaren till den befintliga kunden manuellt"
REVIEW_INVALID = "kunduppgifter kunde inte registreras - granska och lägg upp kunden manuellt"


@dataclass(frozen=True)
class OnboardingOutcome:
    # "created"      - all details in, customer registered
    # "incomplete"   - some details still missing, follow-up sent
    # "needs_review" - parsed but not registered, Control Tower task opened
    status: str
    contact: ContactRecord | None = None


class CustomerOnboardingService:
    def __init__(
        self,
        *,
        parsing_llm: CustomerDetailsParsingLLM,
        customers: CustomerImportService,
        clarification_outbound: ClarificationOutboundRepository,
        task_repository: OperationalTaskWriteRepository,
        agent_logs: AgentLogWriteRepository,
        agent_config: AgentConfigService,
        customer_mailbox: str | None = None,
    ) -> None:
        self._parsing_llm = parsing_llm
        self._customers = customers
        self._clarification_outbound = clarification_outbound
        self._task_repository = task_repository
        self._agent_logs = agent_logs
        self._agent_config = agent_config
        self._customer_mailbox = customer_mailbox

    async def request_details(self, email: InboundEmailRecord) -> None:
        """Asks a sender who just confirmed an order (and isn't a known
        customer) for their company details. `email` is the confirmation.
        """
        bullet_list = "\n".join(f"- {label}" for _, label in REQUIRED_DETAILS)
        body_text = (
            f"{greeting(email.sender_name, email.sender)}\n\n"
            "Tack för din beställning! För att vi ska kunna slutföra den och fakturera "
            "transporten behöver vi några uppgifter om ert företag:\n\n"
            f"{bullet_list}\n\n"
            "Vänligen svara på detta mejl med uppgifterna.\n\n"
            "Med vänlig hälsning,\nSandahls"
        )
        await self._enqueue_reply(email, body_text)
        await self._agent_logs.record(
            agent_key=AGENT_KEY,
            agent_name=AGENT_NAME,
            step=(
                f"Okänd avsändare {email.sender} bekräftade en beställning - "
                "bad om företagsuppgifter"
            ),
            entity_id=email.id,
            confidence=1.0,
        )

    async def handle_reply(
        self, email: InboundEmailRecord, history: list[InboundEmailRecord]
    ) -> OnboardingOutcome | None:
        """Reads a not-yet-registered sender's reply on an accepted quote.

        Returns None when the message carries no company details (the caller
        then handles it like any other reply); otherwise registers the
        customer, or follows up / escalates, and returns what happened.
        """
        parsed = await self._parsing_llm.parse(
            raw_text=_build_thread_text(replies_since_acceptance(history, email), email)
        )
        if not parsed.provides_details:
            return None

        missing = [label for field, label in REQUIRED_DETAILS if not getattr(parsed, field)]
        if missing:
            await self._ask_for_missing(email, missing)
            await self._log(
                email,
                f"Kunduppgifter från {email.sender} ofullständiga - saknar {', '.join(missing)}",
                parsed.confidence,
            )
            return OnboardingOutcome("incomplete")

        config = await self._agent_config.get_config(NORA_CONFIG_KEY)
        if not should_auto_act(config, parsed.confidence):
            await self._escalate(email, REVIEW_LOW_CONFIDENCE)
            return OnboardingOutcome("needs_review")

        try:
            contact = await self._customers.create(_customer_from_details(parsed, email))
        except DuplicateCustomerError as error:
            await self._acknowledge(email, parsed)
            await self._escalate(email, f"{REVIEW_DUPLICATE} ({error})")
            return OnboardingOutcome("needs_review")
        except CustomerValidationError as error:
            await self._escalate(email, f"{REVIEW_INVALID} ({error})")
            return OnboardingOutcome("needs_review")

        await self._acknowledge(email, parsed)
        await self._agent_logs.record(
            agent_key=AGENT_KEY,
            agent_name=AGENT_NAME,
            step=f"Registrerade ny kund {contact.display_name} ({contact.org_number})",
            entity_id=contact.public_id,
            confidence=parsed.confidence,
        )
        return OnboardingOutcome("created", contact)

    async def _ask_for_missing(self, email: InboundEmailRecord, missing: list[str]) -> None:
        bullet_list = "\n".join(f"- {label}" for label in missing)
        body_text = (
            f"{greeting(email.sender_name, email.sender)}\n\n"
            "Tack för uppgifterna! Vi saknar fortfarande:\n\n"
            f"{bullet_list}\n\n"
            "Vänligen svara på detta mejl med de uppgifterna.\n\n"
            "Med vänlig hälsning,\nSandahls"
        )
        await self._enqueue_reply(email, body_text)

    async def _acknowledge(
        self, email: InboundEmailRecord, parsed: ParsedCustomerDetails
    ) -> None:
        body_text = (
            f"{greeting(email.sender_name, email.sender)}\n\n"
            f"Tack! Vi har registrerat {parsed.company_name} "
            f"(org.nr {parsed.org_number}) som kund hos oss. Om något behöver ändras "
            "svarar du bara på detta mejl.\n\n"
            "Med vänlig hälsning,\nSandahls"
        )
        await self._enqueue_reply(email, body_text)

    async def _enqueue_reply(self, email: InboundEmailRecord, body_text: str) -> None:
        subject = email.subject or "din beställning"
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        await self._clarification_outbound.enqueue(
            inbound_email_id=email.id,
            recipient=email.sender,
            subject=subject,
            body_text=body_text,
            in_reply_to_message_id=email.message_id,
            sender_mailbox=self._customer_mailbox,
        )

    async def _escalate(self, email: InboundEmailRecord, reason: str) -> None:
        await self._task_repository.create_task(
            entity_type="email_inbound", entity_id=email.id, reason=reason
        )
        await self._log(email, reason, 0.0)

    async def _log(self, email: InboundEmailRecord, step: str, confidence: float) -> None:
        await self._agent_logs.record(
            agent_key=AGENT_KEY,
            agent_name=AGENT_NAME,
            step=step,
            entity_id=email.id,
            confidence=confidence,
        )


def replies_since_acceptance(
    history: list[InboundEmailRecord], email: InboundEmailRecord
) -> list[InboundEmailRecord]:
    """The messages from `email`'s sender after the order was confirmed - the
    only ones that can hold company details. Everything up to and including
    the confirmation is left out on purpose: the original request talks about
    pickup and delivery addresses, which must never be mistaken for the
    company's own address. With no recorded confirmation, only `email` itself
    is read.
    """
    confirmed_at = max(
        (
            index
            for index, row in enumerate(history)
            if row.classification == ACCEPTED_CLASSIFICATION
        ),
        default=None,
    )
    if confirmed_at is None:
        return []
    return [
        row
        for row in history[confirmed_at + 1 :]
        if row.id != email.id and row.sender.lower() == email.sender.lower()
    ]


def _build_thread_text(prior: list[InboundEmailRecord], email: InboundEmailRecord) -> str:
    segments = [
        f"--- Message from {row.sender} ({row.created_at}) ---\n{row.body_text}" for row in prior
    ]
    segments.append(
        f"--- Message from {email.sender} ({email.created_at}) ---\n{email.body_text}"
    )
    return "\n\n".join(segments)


def _customer_from_details(
    parsed: ParsedCustomerDetails, email: InboundEmailRecord
) -> CustomerInput:
    # `email` (the sender) - not the named contact's address - is the identity
    # inbound mail is matched on, so their next message finds this customer.
    return CustomerInput(
        display_name=parsed.company_name or "",
        email=email.sender,
        org_number=parsed.org_number,
        address=parsed.address,
        contact_person=parsed.contact_person,
        contact_email=parsed.contact_email,
        contact_phone=parsed.contact_phone,
    )
