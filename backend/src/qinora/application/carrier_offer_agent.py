from dataclasses import dataclass

from qinora.application.agent_config import AgentConfigService, should_auto_act
from qinora.application.ports import (
    AgentLogWriteRepository,
    CarrierOfferParsingLLM,
    CarrierOfferWriteRepository,
)
from qinora.application.read_models import (
    AgentLogRecord,
    CarrierOfferRecord,
    ParsedCarrierOfferDraft,
)

AGENT_KEY = "carrier_offer_agent"
AGENT_NAME = "Remy Rates"


@dataclass(frozen=True)
class ParseCarrierOfferCommand:
    request_id: str
    raw_text: str


@dataclass(frozen=True)
class ParseCarrierOfferResult:
    draft: ParsedCarrierOfferDraft
    offer: CarrierOfferRecord | None
    agent_log: AgentLogRecord
    needs_human_review: bool


class CarrierOfferParsingAgent:
    """Reads a carrier's (subcontractor's) free-text reply to a booking/rate
    request and proposes a structured offer. Auto-saves the offer only when
    the "Remy Rates" agent config is enabled with auto_mode/min_confidence
    that clear the draft's own confidence - otherwise the draft is logged
    for a human to review instead, matching the human-in-the-loop principle
    for assisted-mode agents.

    This class is the *only* place application code talks to the LLM, via
    the CarrierOfferParsingLLM port. It has no idea OpenAI exists.
    """

    def __init__(
        self,
        llm: CarrierOfferParsingLLM,
        offers: CarrierOfferWriteRepository,
        agent_logs: AgentLogWriteRepository,
        agent_config: AgentConfigService,
    ) -> None:
        self._llm = llm
        self._offers = offers
        self._agent_logs = agent_logs
        self._agent_config = agent_config

    async def execute(self, command: ParseCarrierOfferCommand) -> ParseCarrierOfferResult:
        draft = await self._llm.parse(raw_text=command.raw_text)
        config = await self._agent_config.get_config(AGENT_KEY)
        can_auto_act = should_auto_act(config, draft.confidence)
        needs_review = not can_auto_act or bool(draft.missing_fields)

        offer: CarrierOfferRecord | None = None
        if not needs_review:
            offer = await self._offers.create_offer(
                request_id=command.request_id,
                carrier_name=draft.carrier_name,
                price=draft.price,
                currency=draft.currency,
                transit_days=draft.transit_days,
                notes=draft.notes,
                confidence=draft.confidence,
            )

        if offer is not None:
            step = f"Parsed offer from {draft.carrier_name} for request {command.request_id}"
            entity_id = offer.id
        else:
            reason = ", ".join(draft.missing_fields) or "confidence below threshold"
            step = (
                f"Low-confidence carrier offer for request {command.request_id}, "
                f"flagged for review ({reason})"
            )
            entity_id = command.request_id

        agent_log = await self._agent_logs.record(
            agent_key=AGENT_KEY,
            agent_name=AGENT_NAME,
            step=step,
            entity_id=entity_id,
            confidence=draft.confidence,
        )

        return ParseCarrierOfferResult(
            draft=draft,
            offer=offer,
            agent_log=agent_log,
            needs_human_review=needs_review,
        )

    async def list_for_request(self, request_id: str) -> list[CarrierOfferRecord]:
        return await self._offers.list_offers_for_request(request_id)
