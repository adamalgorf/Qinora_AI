from fastapi import APIRouter, HTTPException, status

from qinora.application import AuthContext, CreateInvoiceAuditCommand, Role
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    CreateInvoicePayload,
    CreateInvoiceResponse,
    InvoiceListItem,
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


@router.post("/shipments/{shipment_id}/status", response_model=ShipmentListItem)
async def update_shipment_status(
    shipment_id: str,
    payload: UpdateShipmentStatusPayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> ShipmentListItem:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)

    try:
        shipment = await container.shipment_repository.update_status(shipment_id, payload.status)
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
