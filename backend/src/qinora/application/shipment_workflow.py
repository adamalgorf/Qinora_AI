from dataclasses import dataclass

from qinora.application.ports import ShipmentEventRepository, ShipmentWriteRepository
from qinora.application.read_models import ShipmentRecord


@dataclass(frozen=True)
class UpdateShipmentStatusCommand:
    shipment_id: str
    status: str
    reason: str | None = None


class ShipmentWorkflow:
    def __init__(
        self,
        shipment_repository: ShipmentWriteRepository,
        event_repository: ShipmentEventRepository,
    ) -> None:
        self._shipment_repository = shipment_repository
        self._event_repository = event_repository

    async def update_status(self, command: UpdateShipmentStatusCommand) -> ShipmentRecord | None:
        current = await self._shipment_repository.get_shipment(command.shipment_id)
        if current is None:
            return None

        shipment = await self._shipment_repository.update_status(
            command.shipment_id,
            command.status,
        )
        if shipment is None:
            return None

        await self._event_repository.record_status_change(
            shipment_id=command.shipment_id,
            from_status=current.status,
            to_status=shipment.status,
            reason=command.reason,
        )
        return shipment
