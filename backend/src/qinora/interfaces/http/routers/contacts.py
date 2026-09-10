from fastapi import APIRouter, HTTPException, status

from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import CONTAINER
from qinora.interfaces.http.schemas import ContactListItem, CustomerDetailResponse

router = APIRouter()


@router.get("/contacts", response_model=list[ContactListItem])
async def list_contacts(container: AppContainer = CONTAINER) -> list[ContactListItem]:
    return [
        ContactListItem(**item.__dict__)
        for item in await container.operational_queries.list_contacts()
    ]


@router.get("/contacts/{contact_id}", response_model=CustomerDetailResponse)
async def contact_detail(
    contact_id: str,
    container: AppContainer = CONTAINER,
) -> CustomerDetailResponse:
    detail = await container.operational_queries.get_contact_detail(contact_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    return CustomerDetailResponse(
        **detail.contact.__dict__,
        active_jobs=detail.active_jobs,
        active_route=detail.active_route,
        avg_ai_response_minutes=detail.avg_ai_response_minutes,
    )
