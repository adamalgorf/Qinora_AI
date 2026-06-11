from fastapi import APIRouter

from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import CONTAINER
from qinora.interfaces.http.schemas import InboxListItem

router = APIRouter()


@router.get("/inbox/pending", response_model=list[InboxListItem])
async def pending_inbox(container: AppContainer = CONTAINER) -> list[InboxListItem]:
    return [
        InboxListItem(**item.__dict__)
        for item in await container.operational_queries.list_inbox()
    ]
