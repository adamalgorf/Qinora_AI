from fastapi import APIRouter, status

from qinora.application import (
    AuthContext,
    CargoLineCommand,
    CreateRequestCommand,
    Role,
)
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    CreateRequestPayload,
    CreateRequestResponse,
    RequestListItem,
)

router = APIRouter()


@router.get("/requests", response_model=list[RequestListItem])
async def list_requests(container: AppContainer = CONTAINER) -> list[RequestListItem]:
    return [
        RequestListItem(**item.__dict__)
        for item in await container.operational_queries.list_requests()
    ]


@router.post(
    "/requests",
    response_model=CreateRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transport_request(
    payload: CreateRequestPayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> CreateRequestResponse:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    result = await container.create_request.execute(
        CreateRequestCommand(
            customer=payload.customer,
            origin=payload.origin,
            destination=payload.destination,
            mode=payload.mode,
            loading_time=payload.loading_time,
            unloading_time=payload.unloading_time,
            cargo=tuple(
                CargoLineCommand(
                    description=line.description,
                    quantity=line.quantity,
                    weight_kg=line.weight_kg,
                    length_cm=line.length_cm,
                    width_cm=line.width_cm,
                    height_cm=line.height_cm,
                )
                for line in payload.cargo
            ),
        )
    )

    return CreateRequestResponse(
        request=RequestListItem(**result.request.__dict__),
        complete=result.complete,
        review_reason=result.review_reason,
        adr_un_numbers=list(result.adr_un_numbers),
    )
