from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from qinora.application.ports import OperationalTaskWriteRepository, StaleRequestRepository
from qinora.application.read_models import OperationalTaskRecord, StaleRequestRecord


@dataclass(frozen=True)
class EscalateStaleRequestsCommand:
    max_age_hours: int = 24


@dataclass(frozen=True)
class StaleRequestEscalationResult:
    stale_requests: tuple[StaleRequestRecord, ...]
    tasks: tuple[OperationalTaskRecord, ...]


class StaleRequestEscalator:
    def __init__(
        self,
        stale_requests: StaleRequestRepository,
        tasks: OperationalTaskWriteRepository,
    ) -> None:
        self._stale_requests = stale_requests
        self._tasks = tasks

    async def run(
        self,
        command: EscalateStaleRequestsCommand,
    ) -> StaleRequestEscalationResult:
        cutoff = datetime.now(UTC) - timedelta(hours=command.max_age_hours)
        stale_requests = await self._stale_requests.list_stale_requests(
            cutoff.isoformat(timespec="seconds")
        )
        tasks = [
            await self._tasks.create_task(
                entity_type="transport_request",
                entity_id=request.id,
                priority="high",
                reason=_reason(request),
            )
            for request in stale_requests
        ]

        return StaleRequestEscalationResult(
            stale_requests=tuple(stale_requests),
            tasks=tuple(tasks),
        )


def _reason(request: StaleRequestRecord) -> str:
    detail = request.review_reason or "Clarification has not been completed"
    return f"Stale clarification request {request.public_id}: {detail}"
