from dataclasses import dataclass

from qinora.application.ports import AgentLogWriteRepository, ContactReadRepository
from qinora.application.read_models import AgentLogRecord, ContactRecord


@dataclass(frozen=True)
class MatchContactCommand:
    sender: str
    inbound_email_id: str


@dataclass(frozen=True)
class MatchContactResult:
    contact: ContactRecord | None
    agent_log: AgentLogRecord
    confidence: float


class ContactMatchingUseCase:
    def __init__(
        self,
        contacts: ContactReadRepository,
        agent_logs: AgentLogWriteRepository,
    ) -> None:
        self._contacts = contacts
        self._agent_logs = agent_logs

    async def execute(self, command: MatchContactCommand) -> MatchContactResult:
        contact = await self._contacts.find_by_sender(command.sender)
        confidence = 0.92 if contact and contact.email else 0.74 if contact else 0.0
        step = (
            f"Matched {command.sender} to {contact.display_name}"
            if contact
            else f"No CRM contact matched for {command.sender}"
        )
        agent_log = await self._agent_logs.record(
            agent_key="customer_match_agent",
            agent_name="Miles Match",
            step=step,
            entity_id=contact.public_id if contact else command.inbound_email_id,
            confidence=confidence,
        )

        return MatchContactResult(
            contact=contact,
            agent_log=agent_log,
            confidence=confidence,
        )
