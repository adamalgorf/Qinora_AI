from fastapi import APIRouter

from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import CONTAINER
from qinora.interfaces.http.schemas import ContactListItem

router = APIRouter()


@router.get("/contacts", response_model=list[ContactListItem])
async def list_contacts(container: AppContainer = CONTAINER) -> list[ContactListItem]:
    return [
        ContactListItem(
            id=item.id,
            public_id=item.public_id,
            display_name=item.display_name,
            email=item.email,
            domain=item.domain,
            default_markup_percent=item.default_markup_percent,
            default_incoterms=item.default_incoterms,
            payment_terms=item.payment_terms,
        )
        for item in await container.operational_queries.list_contacts()
    ]
