from dataclasses import dataclass
from datetime import datetime

from qinora.application.ports import OperationalTaskWriteRepository, RequestWriteRepository
from qinora.application.read_models import RequestRecord
from qinora.domain import CargoLineInput, TransportMode, TransportRequestInput
from qinora.domain.transport_request import DEFAULT_REQUIRED_FIELDS, validate_transport_request


@dataclass(frozen=True)
class CargoLineCommand:
    description: str
    quantity: int | None
    weight_kg: float | None
    length_cm: float | None
    width_cm: float | None
    height_cm: float | None


@dataclass(frozen=True)
class CreateRequestCommand:
    customer: str
    origin: str
    destination: str
    mode: str
    cargo: tuple[CargoLineCommand, ...]
    loading_time: datetime | None = None
    unloading_time: datetime | None = None


@dataclass(frozen=True)
class CreateRequestResult:
    request: RequestRecord
    complete: bool
    review_reason: str | None
    adr_un_numbers: tuple[str, ...]


class CreateRequestUseCase:
    def __init__(
        self,
        repository: RequestWriteRepository,
        task_repository: OperationalTaskWriteRepository,
    ) -> None:
        self._repository = repository
        self._task_repository = task_repository

    async def execute(
        self,
        command: CreateRequestCommand,
        required_fields: frozenset[str] = DEFAULT_REQUIRED_FIELDS,
    ) -> CreateRequestResult:
        request_input = _to_request_input(command)
        validation = validate_transport_request(request_input, required_fields=required_fields)
        review_reason = None

        if not validation.complete:
            review_reason = "; ".join(issue.message for issue in validation.issues)

        request = await self._repository.create_transport_request(
            customer=command.customer,
            lane=f"{command.origin} -> {command.destination}",
            request=request_input,
            status="parsed" if validation.complete else "needs_clarification",
            review_reason=review_reason,
        )
        if not validation.complete and review_reason:
            await self._task_repository.create_task(
                entity_type="transport_request",
                entity_id=request.id,
                priority="high",
                reason=review_reason,
            )

        return CreateRequestResult(
            request=request,
            complete=validation.complete,
            review_reason=review_reason,
            adr_un_numbers=tuple(finding.un_number for finding in validation.adr_findings),
        )


@dataclass(frozen=True)
class UpdateRequestCommand:
    request_id: str
    customer: str
    origin: str
    destination: str
    mode: str
    cargo: tuple[CargoLineCommand, ...]
    loading_time: datetime | None = None
    unloading_time: datetime | None = None


@dataclass(frozen=True)
class UpdateRequestResult:
    request: RequestRecord
    complete: bool
    review_reason: str | None
    adr_un_numbers: tuple[str, ...]


class UpdateRequestUseCase:
    """Mirrors CreateRequestUseCase, but rewrites an existing transport
    request in place - used when Parsek's classify step (see
    application/request_parsing_agent.py) decides a follow-up email refines
    a request already matched via application/thread_matching.py, rather
    than describing a brand-new one.
    """

    def __init__(
        self,
        repository: RequestWriteRepository,
        task_repository: OperationalTaskWriteRepository,
    ) -> None:
        self._repository = repository
        self._task_repository = task_repository

    async def execute(
        self,
        command: UpdateRequestCommand,
        required_fields: frozenset[str] = DEFAULT_REQUIRED_FIELDS,
    ) -> UpdateRequestResult:
        request_input = _to_request_input(command)
        validation = validate_transport_request(request_input, required_fields=required_fields)
        review_reason = None

        if not validation.complete:
            review_reason = "; ".join(issue.message for issue in validation.issues)

        request = await self._repository.update_transport_request(
            request_id=command.request_id,
            customer=command.customer,
            lane=f"{command.origin} -> {command.destination}",
            request=request_input,
            status="parsed" if validation.complete else "needs_clarification",
            review_reason=review_reason,
        )
        if not validation.complete and review_reason:
            await self._task_repository.create_task(
                entity_type="transport_request",
                entity_id=request.id,
                priority="high",
                reason=review_reason,
            )

        return UpdateRequestResult(
            request=request,
            complete=validation.complete,
            review_reason=review_reason,
            adr_un_numbers=tuple(finding.un_number for finding in validation.adr_findings),
        )


def _to_request_input(
    command: CreateRequestCommand | UpdateRequestCommand,
) -> TransportRequestInput:
    return TransportRequestInput(
        mode=TransportMode(command.mode),
        cargo=tuple(
            CargoLineInput(
                description=line.description,
                quantity=line.quantity,
                weight_kg=line.weight_kg,
                length_cm=line.length_cm,
                width_cm=line.width_cm,
                height_cm=line.height_cm,
            )
            for line in command.cargo
        ),
        loading_time=command.loading_time,
        unloading_time=command.unloading_time,
    )
