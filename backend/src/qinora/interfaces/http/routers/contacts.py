from fastapi import APIRouter, HTTPException, UploadFile, status

from qinora.application import AuthContext, Role
from qinora.application.customer_import import (
    CustomerInput,
    CustomerValidationError,
    parse_customer_csv,
)
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    ContactCreateRequest,
    ContactImportIssue,
    ContactImportResponse,
    ContactListItem,
    CustomerDetailResponse,
)

router = APIRouter()

MAX_IMPORT_FILE_BYTES = 5 * 1024 * 1024


@router.get("/contacts", response_model=list[ContactListItem])
async def list_contacts(container: AppContainer = CONTAINER) -> list[ContactListItem]:
    return [
        ContactListItem(**item.__dict__)
        for item in await container.operational_queries.list_contacts()
    ]


@router.post(
    "/contacts",
    response_model=ContactListItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_contact(
    payload: ContactCreateRequest,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> ContactListItem:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    try:
        contact = await container.customer_import_service.create(
            CustomerInput(**payload.model_dump())
        )
    except CustomerValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return ContactListItem(**contact.__dict__)


@router.post("/contacts/import", response_model=ContactImportResponse)
async def import_contacts(
    file: UploadFile,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> ContactImportResponse:
    """Bulk-creates customers from a CSV file (e.g. an Excel "Spara som CSV"
    export). Rows that duplicate an existing customer (same e-mail or name)
    are skipped; invalid rows are reported without aborting the import.
    """
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    content = await file.read(MAX_IMPORT_FILE_BYTES + 1)
    if len(content) > MAX_IMPORT_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Filen är för stor (max 5 MB)",
        )
    try:
        rows, parse_issues = parse_customer_csv(content)
    except CustomerValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error

    result = await container.customer_import_service.import_rows(rows, parse_issues)
    return ContactImportResponse(
        created=[ContactListItem(**contact.__dict__) for contact in result.created],
        skipped=[ContactImportIssue(**issue.__dict__) for issue in result.skipped],
        errors=[ContactImportIssue(**issue.__dict__) for issue in result.errors],
    )


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
