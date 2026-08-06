from fastapi import APIRouter, HTTPException, status

from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import CONTAINER
from qinora.interfaces.http.schemas import InboxDetailResponse, InboxListItem

router = APIRouter()


@router.get("/inbox/pending", response_model=list[InboxListItem])
async def pending_inbox(container: AppContainer = CONTAINER) -> list[InboxListItem]:
    return [
        InboxListItem(**item.__dict__)
        for item in await container.operational_queries.list_inbox()
    ]


@router.get("/inbox/{message_id}", response_model=InboxDetailResponse)
async def inbox_detail(
    message_id: str,
    container: AppContainer = CONTAINER,
) -> InboxDetailResponse:
    detail = await container.operational_queries.get_inbox_detail(message_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    return InboxDetailResponse(
        message=InboxListItem(**detail.message.__dict__),
        body_text=detail.body_text,
    )
