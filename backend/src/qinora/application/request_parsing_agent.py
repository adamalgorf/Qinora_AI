from dataclasses import dataclass

from qinora.application.agent_config import (
    AgentConfigService,
    is_agent_enabled_for_auto,
    should_auto_act,
)
from qinora.application.greeting import greeting
from qinora.application.ports import (
    AgentLogWriteRepository,
    ClarificationOutboundRepository,
    OperationalTaskWriteRepository,
    RequestParsingLLM,
)
from qinora.application.read_models import (
    AgentConfigRecord,
    AgentLogRecord,
    ParsedTransportRequestDraft,
)
from qinora.application.request_intake import (
    CargoLineCommand,
    CreateRequestCommand,
    CreateRequestResult,
    CreateRequestUseCase,
    UpdateRequestCommand,
    UpdateRequestResult,
    UpdateRequestUseCase,
)
from qinora.domain.transport_request import DEFAULT_REQUIRED_FIELDS, RequestValidationIssue

AGENT_KEY = "request_parsing_agent"
AGENT_NAME = "Nora"

# Swedish labels for the exact field names Nora's own missing_fields list
# uses (see infrastructure/llm/request_parsing.py's SYSTEM_PROMPT) - shown to
# the customer in the auto-clarification email, so these stay in Swedish
# rather than surfacing the raw field name.
MISSING_FIELD_LABELS_SV = {
    "mode": "transportsätt (väg, sjö, flyg, järnväg)",
    "origin": "avsändningsort",
    "destination": "mottagningsort",
    "cargo": "godsuppgifter (antal kolli och beskrivning)",
    "loading_time": "önskad lastningstid",
    "unloading_time": "önskad lossningstid",
    "cargo.weight_kg": "vikt (kg)",
    "cargo.dimensions": "mått (längd x bredd x höjd)",
}


@dataclass(frozen=True)
class ParseFreeTextRequestCommand:
    customer: str
    raw_text: str
    matched_request_id: str | None = None
    inbound_email_id: str | None = None
    sender_email: str = ""
    sender_name: str | None = None
    subject: str = ""
    message_id: str | None = None


@dataclass(frozen=True)
class ParseFreeTextRequestResult:
    draft: ParsedTransportRequestDraft
    request_result: CreateRequestResult | UpdateRequestResult | None
    agent_log: AgentLogRecord
    needs_human_review: bool
    not_relevant: bool = False


class RequestParsingAgent:
    """Reads a customer's free-text RFQ/booking email (or a full thread of
    them) and proposes a structured TransportRequestInput. Auto-creates or
    auto-updates the request whenever the "Nora" agent config (see
    application/agent_config.py) is enabled and not set to manual mode -
    the min_confidence bar only applies while something is still actually
    missing from the extraction (draft.missing_fields), since a merely-low
    confidence score on an otherwise-complete draft isn't a reason to make
    a human do the work instead. Only a genuinely incomplete/uncertain
    extraction, or an admin's own choice to require manual review, ever
    routes to a human - matching the "automate, don't escalate unless
    actually blocked" principle. See execute()'s can_auto_act branch.

    This class is the *only* place application code talks to the LLM, via
    the RequestParsingLLM port. It has no idea OpenAI exists.

    Nora's own classify step (see infrastructure/llm/request_parsing.py)
    decides whether a thread is a new request ("create"), a follow-up on a
    request already on file ("update" - creates a new request instead if
    the caller, typically the email intake orchestrator, can't supply a
    confirmed matched_request_id from application/thread_matching.py -
    see execute()'s final branch), or not a transport request at all
    ("not_relevant" - escalated as an operational task instead of ever
    becoming a request, the one case that still always goes to a human,
    since auto-replying to spam/bounces/out-of-office risks mail loops).
    """

    def __init__(
        self,
        llm: RequestParsingLLM,
        create_request: CreateRequestUseCase,
        agent_logs: AgentLogWriteRepository,
        agent_config: AgentConfigService,
        update_request: UpdateRequestUseCase | None = None,
        task_repository: OperationalTaskWriteRepository | None = None,
        clarification_outbound: ClarificationOutboundRepository | None = None,
        customer_mailbox: str | None = None,
    ) -> None:
        self._llm = llm
        self._create_request = create_request
        self._agent_logs = agent_logs
        self._agent_config = agent_config
        self._update_request = update_request
        self._task_repository = task_repository
        self._clarification_outbound = clarification_outbound
        # Which mailbox clarification requests should be sent from (e.g.
        # test.spedition@sandahls.com) when more than one Outlook bridge
        # instance is running - see workers/outlook_bridge.py. None means
        # "any bridge instance may send it" (single-mailbox deployments).
        self._customer_mailbox = customer_mailbox

    async def execute(self, command: ParseFreeTextRequestCommand) -> ParseFreeTextRequestResult:
        draft = await self._llm.parse(raw_text=command.raw_text)
        config = await self._agent_config.get_config(AGENT_KEY)
        if draft.missing_fields:
            can_auto_act = should_auto_act(config, draft.confidence)
        else:
            # Nothing is actually missing from the extraction - don't let a
            # merely-low confidence score alone force a human review. Still
            # respect an admin's own governance choice (agent disabled, or
            # explicitly set to manual mode) - just not the fuzzy confidence
            # bar, which only exists to catch incomplete/uncertain
            # extractions in the first place. User's explicit call
            # 2026-09-17: tasks should be automated, not escalated to a
            # human when automation isn't actually blocked on anything.
            can_auto_act = is_agent_enabled_for_auto(config)
        needs_review = not can_auto_act or bool(draft.missing_fields)
        required_fields = _required_fields_from_config(config)

        # Deterministic backstop for "multiple cargo lines get summed" -
        # the persisted total (see request_intake.py/infrastructure
        # create_transport_request) is always the sum of draft.cargo, so
        # this never trusts LLM-produced arithmetic for the total weight.
        total_weight_kg = sum(line.weight_kg or 0 for line in draft.cargo)

        request_result: CreateRequestResult | UpdateRequestResult | None = None
        not_relevant = False

        if draft.action == "not_relevant":
            not_relevant = True
            needs_review = True
            if self._task_repository is not None:
                await self._task_repository.create_task(
                    entity_type="email_inbound",
                    entity_id=command.inbound_email_id or "unassigned",
                    reason="Not a transport request, escalated for manual review",
                )
        elif not needs_review and command.matched_request_id and self._update_request is not None:
            # Trust application/thread_matching.py's deterministic match over
            # Nora's own "create" vs "update" call: thread_matching already
            # knows this reply belongs to an existing request (message-id or
            # subject-line correlation, not a guess), so update it in place
            # rather than creating a duplicate - regardless of what draft.action
            # says. The LLM has no visibility into matched_request_id, so its
            # classification here is strictly less informed than ours;
            # reproduced live 2026-09-16 as a duplicate REQ-#### created from a
            # customer's own follow-up reply on an already-open thread.
            request_result = await self._update_request.execute(
                UpdateRequestCommand(
                    request_id=command.matched_request_id,
                    customer=command.customer,
                    origin=draft.origin,
                    destination=draft.destination,
                    mode=draft.mode,
                    cargo=_cargo_commands(draft),
                    loading_time=draft.loading_time,
                    unloading_time=draft.unloading_time,
                ),
                required_fields=required_fields,
            )
        elif not needs_review:
            # Covers both a genuinely new request (draft.action == "create")
            # and Nora believing this continues an existing one but
            # thread_matching finding no confirmed match (draft.action ==
            # "update" with no matched_request_id) - rather than blocking on
            # a human to sort out which request this belongs to, create a
            # new one. Worst case is an extra request a human merges later;
            # leaving the customer waiting on a human to notice and resolve
            # the ambiguity is worse. User's explicit call 2026-09-17.
            request_result = await self._create_request.execute(
                CreateRequestCommand(
                    customer=command.customer,
                    origin=draft.origin,
                    destination=draft.destination,
                    mode=draft.mode,
                    cargo=_cargo_commands(draft),
                    loading_time=draft.loading_time,
                    unloading_time=draft.unloading_time,
                ),
                required_fields=required_fields,
            )

        if request_result is not None:
            verb = "Updated" if draft.action == "update" else "Parsed"
            step = (
                f"{verb} request for {command.customer}: "
                f"{draft.origin} -> {draft.destination} ({total_weight_kg:g} kg)"
            )
            entity_id = request_result.request.public_id
        elif not_relevant:
            step = f"Classified inbound email from {command.customer} as not a transport request"
            entity_id = command.inbound_email_id or "unassigned"
        else:
            reason = ", ".join(draft.missing_fields) or "confidence below threshold"
            step = f"Low-confidence parse for {command.customer}, flagged for review ({reason})"
            entity_id = "unassigned"

        agent_log = await self._agent_logs.record(
            agent_key=AGENT_KEY,
            agent_name=AGENT_NAME,
            step=step,
            entity_id=entity_id,
            confidence=draft.confidence,
        )

        # Every inbound email must get SOME reply - not_relevant is the only
        # deliberate exception (auto-replying to spam/bounces/out-of-office
        # risks mail loops). Every other case that leaves request_result
        # None (missing fields, an "update" Nora couldn't match to an
        # existing request, or - most easily missed - a fully-extracted
        # draft that just isn't confident enough to auto-act on) previously
        # left the customer with total silence until a human happened to
        # open the Inbox review queue. Ask for exactly what's missing when
        # something concretely is; otherwise send a holding acknowledgment
        # rather than nothing, so the customer at least knows their message
        # arrived and is being looked at. Reproduced live 2026-09-17: a
        # fully complete, unambiguous request landed in silent manual
        # review with zero communication back to the sender.
        if (
            request_result is None
            and not not_relevant
            and self._clarification_outbound is not None
            and command.inbound_email_id
            and command.sender_email
        ):
            if draft.missing_fields:
                await self._send_clarification_request(command, draft, draft.missing_fields)
            else:
                await self._send_holding_acknowledgment(command)
        # request_result is not None here means CreateRequestUseCase/
        # UpdateRequestUseCase (application/request_intake.py) ran its own
        # domain-level validate_transport_request check - stricter than, and
        # independent from, Nora's own draft.missing_fields above (e.g. it
        # also requires a loading/unloading time). When THAT check finds the
        # request still incomplete, create_request.execute()/
        # update_request.execute() already opened an internal Control Tower
        # task, but nothing tells the customer - without this, the thread
        # just goes silent from their side even though they're waiting on a
        # reply. Reproduced live 2026-09-16.
        elif (
            request_result is not None
            and not request_result.complete
            and self._clarification_outbound is not None
            and command.inbound_email_id
            and command.sender_email
        ):
            missing_fields = _missing_fields_from_issues(request_result.issues)
            if missing_fields:
                await self._send_clarification_request(command, draft, missing_fields)

        return ParseFreeTextRequestResult(
            draft=draft,
            request_result=request_result,
            agent_log=agent_log,
            needs_human_review=needs_review,
            not_relevant=not_relevant,
        )

    async def _send_clarification_request(
        self,
        command: ParseFreeTextRequestCommand,
        draft: ParsedTransportRequestDraft,
        missing_fields: tuple[str, ...],
    ) -> None:
        labels = dict.fromkeys(
            MISSING_FIELD_LABELS_SV.get(field, field) for field in missing_fields
        )
        bullet_list = "\n".join(f"- {label}" for label in labels)

        original_subject = command.subject or "din förfrågan"
        subject = original_subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        # Matches the "Tack för din transportförfrågan angående ... Vi
        # behöver kompletterande information ..." convention already
        # established in this mailbox's prior clarification emails, rather
        # than inventing new phrasing from scratch. Greets the sender by
        # first name (see application/greeting.py) so this reads like a
        # human wrote it, not a form letter.
        body_text = (
            f"{greeting(command.sender_name, command.sender_email)}\n\n"
            f'Tack för din transportförfrågan angående "{original_subject}". '
            "Vi behöver kompletterande information för att kunna ge dig en offert:\n\n"
            f"{bullet_list}\n\n"
            "Vänligen svara på detta mejl med den saknade informationen så "
            "återkommer vi med en offert.\n\n"
            "Med vänlig hälsning,\nSandahls"
        )

        assert self._clarification_outbound is not None
        assert command.inbound_email_id is not None
        await self._clarification_outbound.enqueue(
            inbound_email_id=command.inbound_email_id,
            recipient=command.sender_email,
            subject=subject,
            body_text=body_text,
            in_reply_to_message_id=command.message_id,
            sender_mailbox=self._customer_mailbox,
        )

    async def _send_holding_acknowledgment(
        self,
        command: ParseFreeTextRequestCommand,
    ) -> None:
        """Sent instead of a clarification request when there's nothing
        concrete left to ask for - Nora extracted the request fully but
        just isn't confident enough to auto-act on it, or classified it as
        an update it couldn't match to an existing request. There's no
        missing_fields bullet list to show here, only a plain acknowledgment
        that the message arrived and a human will follow up - see the
        caller's docstring for why sending nothing at all isn't acceptable.
        """
        original_subject = command.subject or "din förfrågan"
        subject = original_subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        body_text = (
            f"{greeting(command.sender_name, command.sender_email)}\n\n"
            f'Tack för din förfrågan angående "{original_subject}". Vi har tagit emot '
            "den och återkommer med en offert så snart som möjligt.\n\n"
            "Med vänlig hälsning,\nSandahls"
        )

        assert self._clarification_outbound is not None
        assert command.inbound_email_id is not None
        await self._clarification_outbound.enqueue(
            inbound_email_id=command.inbound_email_id,
            recipient=command.sender_email,
            subject=subject,
            body_text=body_text,
            in_reply_to_message_id=command.message_id,
            sender_mailbox=self._customer_mailbox,
        )


def _missing_fields_from_issues(
    issues: tuple[RequestValidationIssue, ...],
) -> tuple[str, ...]:
    """Normalizes domain/transport_request.py's per-cargo-line issue fields
    (e.g. "cargo.0.weight_kg", "cargo.1.length_cm") down to the same small
    set of keys MISSING_FIELD_LABELS_SV/Nora's own missing_fields use, so
    both clarification-email code paths render identical Swedish labels
    instead of leaking a raw internal field path to the customer.
    """
    normalized: list[str] = []
    for issue in issues:
        field = issue.field
        if field == "loading_time":
            normalized.append("loading_time")
        elif field == "cargo":
            normalized.append("cargo")
        elif field.startswith("cargo.") and field.endswith("weight_kg"):
            normalized.append("cargo.weight_kg")
        elif field.startswith("cargo.") and field.endswith(("length_cm", "width_cm", "height_cm")):
            normalized.append("cargo.dimensions")
        else:
            normalized.append(field)
    return tuple(dict.fromkeys(normalized))


def _cargo_commands(draft: ParsedTransportRequestDraft) -> tuple[CargoLineCommand, ...]:
    return tuple(
        CargoLineCommand(
            description=line.description,
            quantity=line.quantity,
            weight_kg=line.weight_kg,
            length_cm=line.length_cm,
            width_cm=line.width_cm,
            height_cm=line.height_cm,
        )
        for line in draft.cargo
    )


def _required_fields_from_config(config: AgentConfigRecord | None) -> frozenset[str]:
    if config is None or not config.config:
        return DEFAULT_REQUIRED_FIELDS
    raw = config.config.get("required_fields")
    if not raw:
        return DEFAULT_REQUIRED_FIELDS
    return frozenset(str(field) for field in raw)
