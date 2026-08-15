"""The real AgentDispatcher (application/ports.py) implementation. Wires
the "email.received" event - fired by EmailWebhookUseCase right after it
saves the inbound row - to application/email_intake_orchestrator.py.

RecordingAgentDispatcher (infrastructure/in_memory.py) remains the
no-op/test double; this is the one actually installed in
interfaces/http/container.py.
"""

from qinora.application.email_intake_orchestrator import EmailIntakeOrchestrator

EMAIL_RECEIVED_EVENT = "email.received"


class EmailIntakeDispatcher:
    def __init__(self, orchestrator: EmailIntakeOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def dispatch(self, *, event_type: str, entity_id: str) -> None:
        if event_type != EMAIL_RECEIVED_EVENT:
            return
        await self._orchestrator.handle(entity_id)
