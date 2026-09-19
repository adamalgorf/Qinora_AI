from dataclasses import dataclass
from enum import StrEnum

from qinora.application.agent_registry import AGENTS
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
# row here - there's nothing to gate. Only the agent roles that actually read
# unstructured human text get a config with a confidence threshold - one row
# per AgentDefinition in application/agent_registry.py, the one place agents
# are defined.
DEFAULT_AGENT_CONFIGS = tuple(
    DefaultAgentConfig(
        agent.key,
        agent.name,
        AgentAutoMode(agent.default_auto_mode),
        agent.default_min_confidence,
    )
    for agent in AGENTS
)

# Names used before the agents were aligned with qinora.se (Nora = intake &
# validation, Quinn = offer & booking, Orion = orchestration & follow-up).
# Database initialization renames stored configs and historical agent_logs
# rows still carrying one of these, so the UI never shows the old names.
LEGACY_AGENT_NAMES = {
    "Parsek": "Nora",
    "Miles Match": "Nora",
    "Remy Rates": "Quinn",
    "Rex Response": "Orion",
}


def is_agent_enabled_for_auto(config: AgentConfigRecord | None) -> bool:
    """The governance half of should_auto_act(), below - deliberate admin
    choices (the agent is disabled, or explicitly set to "manual") - split
    out on its own so a caller that wants to bypass the *confidence* gate
    for some other reason (e.g. request_parsing_agent.py proceeding on a
    fully-extracted draft regardless of a fuzzy confidence score - see its
    execute()) still respects these, rather than accidentally overriding
    an admin's own choice to require a human for this agent entirely.
    """
    if config is None or not config.is_enabled:
        return False
    return config.auto_mode != AgentAutoMode.MANUAL.value


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
    if config is None or not is_agent_enabled_for_auto(config):
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
