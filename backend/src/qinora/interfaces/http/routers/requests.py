from fastapi import APIRouter, HTTPException, status

from qinora.application import (
    AuthContext,
    CargoLineCommand,
    CreateRequestCommand,
    ParseCarrierOfferCommand,
    ParseFreeTextRequestCommand,
    Role,
)
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    CarrierOfferItem,
    CreateRequestPayload,
    CreateRequestResponse,
    ParseCarrierOfferPayload,
    ParseCarrierOfferResponse,
    ParsedCargoLinePayload,
    ParsedCarrierOfferPayload,
    ParsedRequestDraftPayload,
    ParseFreeTextRequestPayload,
    ParseFreeTextRequestResponse,
    RequestCargoLineItem,
    RequestDetailResponse,
    RequestListItem,
)

router = APIRouter()


@router.get("/requests", response_model=list[RequestListItem])
async def list_requests(container: AppContainer = CONTAINER) -> list[RequestListItem]:
    return [
        RequestListItem(**item.__dict__)
        for item in await container.operational_queries.list_requests()
    ]


@router.get("/requests/{request_id}", response_model=RequestDetailResponse)
async def request_detail(
    request_id: str,
    container: AppContainer = CONTAINER,
) -> RequestDetailResponse:
    detail = await container.operational_queries.get_request_detail(request_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    return RequestDetailResponse(
        request=RequestListItem(**detail.request.__dict__),
        review_reason=detail.review_reason,
        created_at=detail.created_at,
        cargo_lines=[RequestCargoLineItem(**line.__dict__) for line in detail.cargo_lines],
    )


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


@router.post(
    "/requests/parse",
    response_model=ParseFreeTextRequestResponse,
    status_code=status.HTTP_200_OK,
)
async def parse_free_text_request(
    payload: ParseFreeTextRequestPayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> ParseFreeTextRequestResponse:
    """Runs the "Parsek" agent over free text (e.g. an RFQ email body) and,
    if confident enough, creates the transport request. Low-confidence or
    incomplete drafts are logged for human review instead of auto-created.
    """
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    result = await container.request_parsing_agent.execute(
        ParseFreeTextRequestCommand(customer=payload.customer, raw_text=payload.raw_text)
    )

    return ParseFreeTextRequestResponse(
        draft=ParsedRequestDraftPayload(
            mode=result.draft.mode,
            origin=result.draft.origin,
            destination=result.draft.destination,
            cargo=[ParsedCargoLinePayload(**line.__dict__) for line in result.draft.cargo],
            loading_time=result.draft.loading_time,
            unloading_time=result.draft.unloading_time,
            confidence=result.draft.confidence,
            missing_fields=list(result.draft.missing_fields),
        ),
        needs_human_review=result.needs_human_review,
        request=(
            RequestListItem(**result.request_result.request.__dict__)
            if result.request_result
            else None
        ),
        agent_confidence=result.agent_log.confidence,
    )


@router.post(
    "/requests/{request_id}/carrier-offers/parse",
    response_model=ParseCarrierOfferResponse,
    status_code=status.HTTP_200_OK,
)
async def parse_carrier_offer(
    request_id: str,
    payload: ParseCarrierOfferPayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> ParseCarrierOfferResponse:
    """Runs the "Remy Rates" agent over a carrier's free-text reply (e.g. a
    rate-request email) and, if confident enough, saves it as a structured
    offer against the request. Low-confidence or incomplete drafts are
    logged for human review instead of auto-saved.
    """
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    result = await container.carrier_offer_agent.execute(
        ParseCarrierOfferCommand(request_id=request_id, raw_text=payload.raw_text)
    )

    return ParseCarrierOfferResponse(
        draft=ParsedCarrierOfferPayload(**result.draft.__dict__),
        needs_human_review=result.needs_human_review,
        offer=CarrierOfferItem(**result.offer.__dict__) if result.offer else None,
        agent_confidence=result.agent_log.confidence,
    )


@router.get(
    "/requests/{request_id}/carrier-offers",
    response_model=list[CarrierOfferItem],
)
async def list_carrier_offers(
    request_id: str,
    container: AppContainer = CONTAINER,
) -> list[CarrierOfferItem]:
    offers = await container.carrier_offer_agent.list_for_request(request_id)
    return [CarrierOfferItem(**offer.__dict__) for offer in offers]
