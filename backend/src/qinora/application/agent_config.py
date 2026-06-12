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


DEFAULT_AGENT_CONFIGS = (
    DefaultAgentConfig("intake_agent", "Nora Intake", AgentAutoMode.ASSISTED, 0.7),
    DefaultAgentConfig("customer_match_agent", "Miles Match", AgentAutoMode.ASSISTED, 0.72),
    DefaultAgentConfig("request_parsing_agent", "Parsek", AgentAutoMode.ASSISTED, 0.74),
    DefaultAgentConfig("validation_agent", "Vera Validate", AgentAutoMode.GUARDED_AUTO, 0.8),
    DefaultAgentConfig("quote_agent", "Quinn Quote", AgentAutoMode.MANUAL, 0.85),
    DefaultAgentConfig("quote_response_agent", "Rex Response", AgentAutoMode.ASSISTED, 0.7),
    DefaultAgentConfig("booking_agent", "Bex Booking", AgentAutoMode.MANUAL, 0.82),
    DefaultAgentConfig(
        "carrier_intelligence",
        "Carrier Intelligence",
        AgentAutoMode.ASSISTED,
        0.65,
    ),
    DefaultAgentConfig("tracking_agent", "Trak Flow", AgentAutoMode.GUARDED_AUTO, 0.75),
    DefaultAgentConfig("invoice_audit_agent", "Auri Audit", AgentAutoMode.ASSISTED, 0.8),
    DefaultAgentConfig("dispatcher", "Cy Dispatch", AgentAutoMode.GUARDED_AUTO, 0.7),
)


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
