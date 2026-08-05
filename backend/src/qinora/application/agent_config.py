from dataclasses import dataclass
from enum import StrEnum

from qinora.application.ports import AgentConfigRepository
from qinora.application.read_models import AgentConfigRecord


class AgentAutoMode(StrEnum):
    MANUAL = "manual"
    ASSISTED = "assisted"
    GUARDED_AUTO = "guarded_auto"


@dataclass(frozen=True)
class DefaultAgentConfig:
    agent_key: str
    agent_name: str
    auto_mode: AgentAutoMode
    min_confidence: float


# Every other business step (matching, pricing, booking, dispatch, invoice
# audit) is deterministic code, not an LLM call, so it doesn't get a config
# row here - there's nothing to gate. Only the 3 steps that actually read
# unstructured human text get a real agent with a confidence threshold.
DEFAULT_AGENT_CONFIGS = (
    DefaultAgentConfig("request_parsing_agent", "Parsek", AgentAutoMode.GUARDED_AUTO, 0.74),
    DefaultAgentConfig("carrier_offer_agent", "Remy Rates", AgentAutoMode.GUARDED_AUTO, 0.7),
    DefaultAgentConfig("quote_response_agent", "Rex Response", AgentAutoMode.GUARDED_AUTO, 0.7),
)


def should_auto_act(config: AgentConfigRecord | None, confidence: float) -> bool:
    """Whether an AI agent should act automatically, or flag its result for
    human review, given its configured auto_mode/min_confidence.

    - manual: never auto-act, every result is routed to a human.
    - assisted / guarded_auto: auto-act once confidence clears the
      configured threshold, otherwise flag for review. The two modes gate
      the same way today; guarded_auto is a more-trusted label admins can
      pick, not a separate code path.
    - Missing config (agent not found, or disabled) never auto-acts.
    """
    if config is None or not config.is_enabled:
        return False
    if config.auto_mode == AgentAutoMode.MANUAL.value:
        return False
    return confidence >= config.min_confidence


@dataclass(frozen=True)
class UpdateAgentConfigCommand:
    agent_key: str
    is_enabled: bool
    auto_mode: str
    min_confidence: float


class AgentConfigService:
    def __init__(self, repository: AgentConfigRepository) -> None:
        self._repository = repository

    async def list_configs(self) -> list[AgentConfigRecord]:
        return await self._repository.list_configs()

    async def get_config(self, agent_key: str) -> AgentConfigRecord | None:
        for config in await self._repository.list_configs():
            if config.agent_key == agent_key:
                return config
        return None

    async def update_config(self, command: UpdateAgentConfigCommand) -> AgentConfigRecord:
        if command.auto_mode not in {mode.value for mode in AgentAutoMode}:
            raise ValueError(f"Unsupported auto mode: {command.auto_mode}")
        if command.min_confidence < 0 or command.min_confidence > 1:
            raise ValueError("min_confidence must be between 0 and 1")

        return await self._repository.update_config(
            agent_key=command.agent_key,
            is_enabled=command.is_enabled,
            auto_mode=command.auto_mode,
            min_confidence=command.min_confidence,
        )
