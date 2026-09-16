from fastapi import APIRouter, HTTPException, status

from qinora.application import AuthContext, Role
from qinora.application.case_notes import AddCaseNoteCommand
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    CaseActivityItem,
    CaseDetailResponse,
    CaseEmailItem,
    CaseListItem,
    ContactListItem,
    CreateCaseNotePayload,
    DocumentListItem,
    InternalNoteItem,
    InvoiceListItem,
    QuoteListItem,
    RequestCargoLineItem,
    RequestDetailResponse,
    RequestListItem,
    ShipmentListItem,
)

router = APIRouter()


@router.get("/cases", response_model=list[CaseListItem])
async def list_cases(container: AppContainer = CONTAINER) -> list[CaseListItem]:
    return [
        CaseListItem(**item.__dict__) for item in await container.operational_queries.list_cases()
    ]


@router.get("/cases/{request_id}", response_model=CaseDetailResponse)
async def case_detail(
    request_id: str,
    container: AppContainer = CONTAINER,
) -> CaseDetailResponse:
    detail = await container.operational_queries.get_case_detail(request_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    return CaseDetailResponse(
        case=CaseListItem(**detail.case.__dict__),
        request_detail=RequestDetailResponse(
            request=RequestListItem(**detail.request_detail.request.__dict__),
            review_reason=detail.request_detail.review_reason,
            created_at=detail.request_detail.created_at,
            cargo_lines=[
                RequestCargoLineItem(**line.__dict__)
                for line in detail.request_detail.cargo_lines
            ],
        ),
        quotes=[QuoteListItem(**quote.__dict__) for quote in detail.quotes],
        shipment=ShipmentListItem(**detail.shipment.__dict__) if detail.shipment else None,
        invoice=InvoiceListItem(**detail.invoice.__dict__) if detail.invoice else None,
        documents=[DocumentListItem(**doc.__dict__) for doc in detail.documents],
        contact=ContactListItem(**detail.contact.__dict__) if detail.contact else None,
        notes=[InternalNoteItem(**note.__dict__) for note in detail.notes],
        activity=[CaseActivityItem(**entry) for entry in detail.activity],
        emails=[CaseEmailItem(**entry) for entry in detail.emails],
    )


@router.get("/cases/{request_id}/notes", response_model=list[InternalNoteItem])
async def list_case_notes(
    request_id: str,
    container: AppContainer = CONTAINER,
) -> list[InternalNoteItem]:
    return [
        InternalNoteItem(**note.__dict__)
        for note in await container.operational_queries.list_case_notes(request_id)
    ]


@router.post(
    "/cases/{request_id}/notes",
    response_model=InternalNoteItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_case_note(
    request_id: str,
    payload: CreateCaseNotePayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> InternalNoteItem:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    note = await container.case_notes_service.add_note(
        AddCaseNoteCommand(
            request_id=request_id,
            author=payload.author,
            body_text=payload.body_text,
        )
    )
    return InternalNoteItem(**note.__dict__)
