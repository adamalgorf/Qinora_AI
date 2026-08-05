from dataclasses import dataclass

from qinora.application.agent_config import AgentConfigService, should_auto_act
from qinora.application.ports import AgentLogWriteRepository, RequestParsingLLM
from qinora.application.read_models import AgentLogRecord, ParsedTransportRequestDraft
from qinora.application.request_intake import (
    CargoLineCommand,
    CreateRequestCommand,
    CreateRequestResult,
    CreateRequestUseCase,
)

AGENT_KEY = "request_parsing_agent"
AGENT_NAME = "Parsek"


@dataclass(frozen=True)
class ParseFreeTextRequestCommand:
    customer: str
    raw_text: str


@dataclass(frozen=True)
class ParseFreeTextRequestResult:
    draft: ParsedTransportRequestDraft
    request_result: CreateRequestResult | None
    agent_log: AgentLogRecord
    needs_human_review: bool


class RequestParsingAgent:
    """Reads a customer's free-text RFQ/booking email and proposes a
    structured TransportRequestInput. Auto-creates the request only when
    the "Parsek" agent config (see application/agent_config.py) is enabled
    with auto_mode/min_confidence that clear the draft's own confidence -
    otherwise the draft is logged for a human to review instead, matching
    the human-in-the-loop principle for assisted-mode agents.

    This class is the *only* place application code talks to the LLM, via
    the RequestParsingLLM port. It has no idea OpenAI exists.
    """

    def __init__(
        self,
        llm: RequestParsingLLM,
        create_request: CreateRequestUseCase,
        agent_logs: AgentLogWriteRepository,
        agent_config: AgentConfigService,
    ) -> None:
        self._llm = llm
        self._create_request = create_request
        self._agent_logs = agent_logs
        self._agent_config = agent_config

    async def execute(self, command: ParseFreeTextRequestCommand) -> ParseFreeTextRequestResult:
        draft = await self._llm.parse(raw_text=command.raw_text)
        config = await self._agent_config.get_config(AGENT_KEY)
        can_auto_act = should_auto_act(config, draft.confidence)
        needs_review = not can_auto_act or bool(draft.missing_fields)

        request_result: CreateRequestResult | None = None
        if not needs_review:
            request_result = await self._create_request.execute(
                CreateRequestCommand(
                    customer=command.customer,
                    origin=draft.origin,
                    destination=draft.destination,
                    mode=draft.mode,
                    cargo=tuple(
                        CargoLineCommand(
                            description=line.description,
                            quantity=line.quantity,
                            weight_kg=line.weight_kg,
                            length_cm=line.length_cm,
                            width_cm=line.width_cm,
                            height_cm=line.height_cm,
                        )
                        for line in draft.cargo
                    ),
                    loading_time=draft.loading_time,
                    unloading_time=draft.unloading_time,
                )
            )

        if request_result is not None:
            step = (
                f"Parsed request for {command.customer}: "
                f"{draft.origin} -> {draft.destination}"
            )
            entity_id = request_result.request.public_id
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

        return ParseFreeTextRequestResult(
            draft=draft,
            request_result=request_result,
            agent_log=agent_log,
            needs_human_review=needs_review,
        )
