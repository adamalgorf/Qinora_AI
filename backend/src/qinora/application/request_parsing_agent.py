from dataclasses import dataclass

from qinora.application.agent_config import AgentConfigService, should_auto_act
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
from qinora.domain.transport_request import DEFAULT_REQUIRED_FIELDS

AGENT_KEY = "request_parsing_agent"
AGENT_NAME = "Parsek"

# Swedish labels for the exact field names Parsek's own missing_fields list
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
    subject: str = ""


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
    auto-updates the request only when the "Parsek" agent config (see
    application/agent_config.py) is enabled with auto_mode/min_confidence
    that clear the draft's own confidence - otherwise the draft is logged
    for a human to review instead, matching the human-in-the-loop principle
    for assisted-mode agents.

    This class is the *only* place application code talks to the LLM, via
    the RequestParsingLLM port. It has no idea OpenAI exists.

    Parsek's own classify step (see infrastructure/llm/request_parsing.py)
    decides whether a thread is a new request ("create"), a follow-up on a
    request already on file ("update" - only actionable when the caller,
    typically the email intake orchestrator, also supplies
    matched_request_id from application/thread_matching.py), or not a
    transport request at all ("not_relevant" - escalated as an operational
    task instead of ever becoming a request).
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
    ) -> None:
        self._llm = llm
        self._create_request = create_request
        self._agent_logs = agent_logs
        self._agent_config = agent_config
        self._update_request = update_request
        self._task_repository = task_repository
        self._clarification_outbound = clarification_outbound

    async def execute(self, command: ParseFreeTextRequestCommand) -> ParseFreeTextRequestResult:
        draft = await self._llm.parse(raw_text=command.raw_text)
        config = await self._agent_config.get_config(AGENT_KEY)
        can_auto_act = should_auto_act(config, draft.confidence)
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
        elif not needs_review and draft.action == "update":
            if command.matched_request_id and self._update_request is not None:
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
            else:
                needs_review = True
                if self._task_repository is not None:
                    await self._task_repository.create_task(
                        entity_type="email_inbound",
                        entity_id=command.inbound_email_id or "unassigned",
                        reason="Classified as an update but no matching request was found",
                    )
        elif not needs_review:
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

        # A genuine "text was too vague/incomplete" outcome (as opposed to
        # not_relevant, or the update-with-no-matching-request case, which
        # has already been escalated as a task above) - ask the customer
        # for exactly what's missing instead of leaving the thread to go
        # stale until someone reviews the Inbox by hand.
        if (
            request_result is None
            and not not_relevant
            and draft.missing_fields
            and self._clarification_outbound is not None
            and command.inbound_email_id
            and command.sender_email
        ):
            await self._send_clarification_request(command, draft)

        return ParseFreeTextRequestResult(
            draft=draft,
            request_result=request_result,
            agent_log=agent_log,
            needs_human_review=needs_review,
            not_relevant=not_relevant,
        )

    async def _send_clarification_request(
        self, command: ParseFreeTextRequestCommand, draft: ParsedTransportRequestDraft
    ) -> None:
        labels = [MISSING_FIELD_LABELS_SV.get(field, field) for field in draft.missing_fields]
        bullet_list = "\n".join(f"- {label}" for label in labels)

        subject = command.subject or "Din fraktförfrågan"
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        body_text = (
            "Hej,\n\n"
            "Tack för din förfrågan! För att kunna ta fram en offert behöver vi "
            "lite mer information:\n\n"
            f"{bullet_list}\n\n"
            "Svara gärna på detta mail med uppgifterna, så återkommer vi med en offert.\n\n"
            "Med vänlig hälsning,\nSandahls"
        )

        assert self._clarification_outbound is not None
        assert command.inbound_email_id is not None
        await self._clarification_outbound.enqueue(
            inbound_email_id=command.inbound_email_id,
            recipient=command.sender_email,
            subject=subject,
            body_text=body_text,
        )


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
