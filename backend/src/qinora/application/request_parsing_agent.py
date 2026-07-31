from dataclasses import dataclass

from qinora.application.ports import AgentLogWriteRepository, RequestParsingLLM
from qinora.application.read_models import AgentLogRecord, ParsedTransportRequestDraft
from qinora.application.request_intake import (
    CargoLineCommand,
    CreateRequestCommand,
    CreateRequestResult,
    CreateRequestUseCase,
)

# Mirrors the "request_parsing_agent" entry in agent_config.DEFAULT_AGENT_CONFIGS.
# Kept as a local constant (rather than importing DEFAULT_AGENT_CONFIGS) so this
# use case doesn't depend on config wiring - the runtime min_confidence for the
# *enabled* agent should ultimately come from AgentConfigService, see note in
# execute() below.
AGENT_KEY = "request_parsing_agent"
AGENT_NAME = "Parsek"
FALLBACK_MIN_CONFIDENCE = 0.74


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
    """Reasoning agent (per the Qinora capability map's agent paradigm):
    interprets unstructured RFQ/request text and proposes a structured
    TransportRequestInput. It never acts autonomously past the configured
    confidence threshold - low-confidence or incomplete drafts are logged
    but not persisted as a request, matching the human-in-the-loop
    principle for assisted-mode agents.

    This class is the *only* place application code talks to the LLM,
    via the RequestParsingLLM port. It has no idea LangChain exists.
    """

    def __init__(
        self,
        llm: RequestParsingLLM,
        create_request: CreateRequestUseCase,
        agent_logs: AgentLogWriteRepository,
        min_confidence: float = FALLBACK_MIN_CONFIDENCE,
    ) -> None:
        self._llm = llm
        self._create_request = create_request
        self._agent_logs = agent_logs
        self._min_confidence = min_confidence

    async def execute(self, command: ParseFreeTextRequestCommand) -> ParseFreeTextRequestResult:
        draft = await self._llm.parse(raw_text=command.raw_text)
        needs_review = draft.confidence < self._min_confidence or bool(draft.missing_fields)

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
