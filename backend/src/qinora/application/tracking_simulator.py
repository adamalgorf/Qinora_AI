from dataclasses import dataclass

from qinora.application.invoice_audit import CreateInvoiceAuditCommand, InvoiceAuditWorkflow
from qinora.application.operational_queries import OperationalQueries
from qinora.application.ports import InvoiceWriteRepository
from qinora.application.read_models import InvoiceRecord, ShipmentRecord
from qinora.application.shipment_workflow import ShipmentWorkflow, UpdateShipmentStatusCommand


@dataclass(frozen=True)
class RunTrackingSimulatorCommand:
    limit: int = 10
    max_discrepancy: float = 250


@dataclass(frozen=True)
class TrackingSimulatorResult:
    delivered: tuple[ShipmentRecord, ...]
    invoices: tuple[InvoiceRecord, ...]


class TrackingSimulator:
    def __init__(
        self,
        operational_queries: OperationalQueries,
        shipment_workflow: ShipmentWorkflow,
        invoice_repository: InvoiceWriteRepository,
        invoice_audit: InvoiceAuditWorkflow,
    ) -> None:
        self._operational_queries = operational_queries
        self._shipment_workflow = shipment_workflow
        self._invoice_repository = invoice_repository
        self._invoice_audit = invoice_audit

    async def run(self, command: RunTrackingSimulatorCommand) -> TrackingSimulatorResult:
        in_transit = [
            shipment
            for shipment in await self._operational_queries.list_shipments()
            if shipment.status == "in_transit"
        ][: command.limit]
        delivered: list[ShipmentRecord] = []
        invoices: list[InvoiceRecord] = []

        for shipment in in_transit:
            delivered_shipment = await self._shipment_workflow.update_status(
                UpdateShipmentStatusCommand(
                    shipment_id=shipment.id,
                    status="delivered",
                    reason="Tracking simulator delivered shipment",
                )
            )
            if delivered_shipment is None:
                continue

            delivered.append(delivered_shipment)
            expected_amount = await self._invoice_repository.expected_invoice_amount(shipment.id)
            audit = await self._invoice_audit.audit_invoice(
                CreateInvoiceAuditCommand(
                    shipment_id=shipment.id,
                    invoice_amount=expected_amount,
                    max_discrepancy=command.max_discrepancy,
                )
            )
            invoices.append(audit.invoice)

        return TrackingSimulatorResult(delivered=tuple(delivered), invoices=tuple(invoices))
