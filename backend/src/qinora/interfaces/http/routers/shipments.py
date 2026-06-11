from fastapi import APIRouter, HTTPException, status

from qinora.application import (
    AuthContext,
    CreateInvoiceAuditCommand,
    Role,
    UpdateShipmentStatusCommand,
)
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    CreateInvoicePayload,
    CreateInvoiceResponse,
    InvoiceListItem,
    ShipmentEventItem,
    ShipmentListItem,
    UpdateShipmentStatusPayload,
)

router = APIRouter()


@router.get("/shipments", response_model=list[ShipmentListItem])
async def list_shipments(container: AppContainer = CONTAINER) -> list[ShipmentListItem]:
    return [
        ShipmentListItem(**item.__dict__)
        for item in await container.operational_queries.list_shipments()
    ]


@router.get("/invoices", response_model=list[InvoiceListItem])
async def list_invoices(container: AppContainer = CONTAINER) -> list[InvoiceListItem]:
    return [
        InvoiceListItem(**item.__dict__)
        for item in await container.operational_queries.list_invoices()
    ]


@router.get("/shipments/{shipment_id}/timeline", response_model=list[ShipmentEventItem])
async def shipment_timeline(
    shipment_id: str,
    container: AppContainer = CONTAINER,
) -> list[ShipmentEventItem]:
    return [
        ShipmentEventItem(**item.__dict__)
        for item in await container.operational_queries.list_shipment_events(shipment_id)
    ]


@router.post("/shipments/{shipment_id}/status", response_model=ShipmentListItem)
async def update_shipment_status(
    shipment_id: str,
    payload: UpdateShipmentStatusPayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> ShipmentListItem:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)

    try:
        shipment = await container.shipment_workflow.update_status(
            UpdateShipmentStatusCommand(
                shipment_id=shipment_id,
                status=payload.status,
                reason="Manual status update",
            )
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    return ShipmentListItem(**shipment.__dict__)


@router.post("/shipments/{shipment_id}/invoice", response_model=CreateInvoiceResponse)
async def create_invoice(
    shipment_id: str,
    payload: CreateInvoicePayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> CreateInvoiceResponse:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)

    try:
        result = await container.invoice_audit.audit_invoice(
            CreateInvoiceAuditCommand(
                shipment_id=shipment_id,
                invoice_amount=payload.invoice_amount,
                max_discrepancy=payload.max_discrepancy,
            )
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return CreateInvoiceResponse(
        invoice=InvoiceListItem(**result.invoice.__dict__),
        shipment_status=result.shipment_status,
    )
