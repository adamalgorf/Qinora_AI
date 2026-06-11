from dataclasses import dataclass

from qinora.application.ports import InvoiceWriteRepository
from qinora.application.read_models import InvoiceRecord
from qinora.application.shipment_workflow import ShipmentWorkflow, UpdateShipmentStatusCommand


@dataclass(frozen=True)
class CreateInvoiceAuditCommand:
    shipment_id: str
    invoice_amount: float
    max_discrepancy: float = 250


@dataclass(frozen=True)
class InvoiceAuditResult:
    invoice: InvoiceRecord
    shipment_status: str


class InvoiceAuditWorkflow:
    def __init__(
        self,
        invoice_repository: InvoiceWriteRepository,
        shipment_workflow: ShipmentWorkflow,
    ) -> None:
        self._invoice_repository = invoice_repository
        self._shipment_workflow = shipment_workflow

    async def audit_invoice(self, command: CreateInvoiceAuditCommand) -> InvoiceAuditResult:
        invoice = await self._invoice_repository.create_invoice_audit(
            shipment_id=command.shipment_id,
            invoice_amount=command.invoice_amount,
            max_discrepancy=command.max_discrepancy,
        )
        shipment_status = "invoice_approved" if invoice.status == "approved" else "invoice_disputed"
        await self._shipment_workflow.update_status(
            UpdateShipmentStatusCommand(
                shipment_id=command.shipment_id,
                status=shipment_status,
                reason="Invoice audit result",
            )
        )

        return InvoiceAuditResult(invoice=invoice, shipment_status=shipment_status)
