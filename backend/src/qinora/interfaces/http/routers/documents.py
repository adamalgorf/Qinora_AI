from fastapi import APIRouter, Form, HTTPException, Response, UploadFile, status

from qinora.application import AuthContext, Role
from qinora.application.document_intake import UnsupportedDocumentError, UploadDocumentCommand
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    CreateDocumentResponse,
    DocumentDetailResponse,
    DocumentListItem,
)

router = APIRouter()


@router.get("/documents", response_model=list[DocumentListItem])
async def list_documents(container: AppContainer = CONTAINER) -> list[DocumentListItem]:
    return [
        DocumentListItem(**item.__dict__)
        for item in await container.operational_queries.list_documents()
    ]


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def document_detail(
    document_id: str,
    container: AppContainer = CONTAINER,
) -> DocumentDetailResponse:
    detail = await container.document_repository.get_document(document_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return DocumentDetailResponse(
        document=DocumentListItem(**detail.document.__dict__),
        extracted_fields=detail.extracted_fields,
    )


@router.get("/documents/{document_id}/content")
async def document_content(
    document_id: str,
    container: AppContainer = CONTAINER,
) -> Response:
    content = await container.document_repository.get_document_content(document_id)
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return Response(
        content=content.content,
        media_type=content.content_type,
        headers={"Content-Disposition": f'inline; filename="{content.filename}"'},
    )


@router.post(
    "/documents",
    response_model=CreateDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile,
    document_type: str | None = Form(default=None),
    request_id: str | None = Form(default=None),
    shipment_id: str | None = Form(default=None),
    contact_id: str | None = Form(default=None),
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> CreateDocumentResponse:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    content = await file.read()

    try:
        record = await container.document_intake_service.upload(
            UploadDocumentCommand(
                filename=file.filename or "document",
                content_type=file.content_type or "application/octet-stream",
                content=content,
                document_type=document_type,
                request_id=request_id,
                shipment_id=shipment_id,
                contact_id=contact_id,
                uploaded_by=context.user_id,
            )
        )
    except UnsupportedDocumentError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return CreateDocumentResponse(**record.__dict__)
