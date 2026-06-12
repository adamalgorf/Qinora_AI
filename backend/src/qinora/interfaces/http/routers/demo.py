from fastapi import APIRouter

from qinora.application import AuthContext, Role
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    DemoFlowResponse,
    InvoiceListItem,
    OutboundReplyItem,
    QuoteListItem,
    RequestListItem,
    ShipmentListItem,
)

router = APIRouter()


@router.post("/demo/flow", response_model=DemoFlowResponse)
async def run_demo_flow(
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> DemoFlowResponse:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    result = await container.demo_flow.run()
    outbound_reply = next(
        (
            reply
            for reply in result.outbound_queue.sent
            if reply.quote_id == result.quote.quote.id
        ),
        result.quote.outbound_reply,
    )

    return DemoFlowResponse(
        steps=list(result.steps),
        request=RequestListItem(**result.request.__dict__),
        quote=QuoteListItem(**result.quote.quote.__dict__),
        outbound_reply=OutboundReplyItem(**outbound_reply.__dict__),
        shipment=ShipmentListItem(**result.final_shipment.__dict__),
        invoice=InvoiceListItem(**result.invoice.invoice.__dict__),
        shipment_status=result.invoice.shipment_status,
    )
