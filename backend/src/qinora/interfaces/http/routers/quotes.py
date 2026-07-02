from fastapi import APIRouter, HTTPException, status

from qinora.application import (
    AuthContext,
    BookQuoteCommand,
    CreateQuoteCommand,
    InterpretQuoteReplyCommand,
    PricingGateError,
    ProcessOutboundQueueCommand,
    QuoteNotFoundError,
    RequestNotFoundError,
    RequestNotQuotableError,
    Role,
    SendQuoteCommand,
)
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    AcceptQuotePayload,
    AcceptQuoteResponse,
    CreateQuotePayload,
    OutboundReplyItem,
    ProcessOutboundQueuePayload,
    ProcessOutboundQueueResponse,
    QuoteAcceptanceEventItem,
    QuoteDetailResponse,
    QuoteLineItem,
    QuoteListItem,
    QuoteReplyPayload,
    QuoteReplyResponse,
    QuoteResponseEventItem,
    SendQuoteResponse,
    ShipmentListItem,
)

router = APIRouter()


@router.get("/quotes", response_model=list[QuoteListItem])
async def list_quotes(container: AppContainer = CONTAINER) -> list[QuoteListItem]:
    return [
        QuoteListItem(**item.__dict__)
        for item in await container.operational_queries.list_quotes()
    ]


@router.get("/quotes/{quote_id}", response_model=QuoteDetailResponse)
async def quote_detail(
    quote_id: str,
    container: AppContainer = CONTAINER,
) -> QuoteDetailResponse:
    detail = await container.operational_queries.get_quote_detail(quote_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")

    return QuoteDetailResponse(
        quote=QuoteListItem(**detail.quote.__dict__),
        line_items=[QuoteLineItem(**item.__dict__) for item in detail.line_items],
        acceptance_events=[
            QuoteAcceptanceEventItem(**item.__dict__) for item in detail.acceptance_events
        ],
    )


@router.post("/quotes", response_model=QuoteListItem, status_code=status.HTTP_201_CREATED)
async def create_quote(
    payload: CreateQuotePayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> QuoteListItem:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    try:
        quote = await container.quote_workflow.create_quote(
            CreateQuoteCommand(
                request_id=payload.request_id,
                customer_price=payload.customer_price,
                currency=payload.currency,
            )
        )
    except RequestNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        ) from error
    except RequestNotQuotableError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return QuoteListItem(**quote.__dict__)


@router.get("/emails/outbound", response_model=list[OutboundReplyItem])
async def list_outbound_replies(
    container: AppContainer = CONTAINER,
) -> list[OutboundReplyItem]:
    return [
        OutboundReplyItem(**item.__dict__)
        for item in await container.operational_queries.list_outbound_replies()
    ]


@router.post("/emails/outbound/process", response_model=ProcessOutboundQueueResponse)
async def process_outbound_replies(
    payload: ProcessOutboundQueuePayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> ProcessOutboundQueueResponse:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    result = await container.process_outbound_queue.execute(
        ProcessOutboundQueueCommand(limit=payload.limit)
    )
    return ProcessOutboundQueueResponse(
        sent=[OutboundReplyItem(**item.__dict__) for item in result.sent],
        failed=[OutboundReplyItem(**item.__dict__) for item in result.failed],
    )


@router.post("/quotes/{quote_id}/send", response_model=SendQuoteResponse)
async def send_quote(
    quote_id: str,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> SendQuoteResponse:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)

    try:
        result = await container.quote_workflow.send_quote(SendQuoteCommand(quote_id=quote_id))
    except QuoteNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        ) from error
    except PricingGateError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return SendQuoteResponse(
        quote=QuoteListItem(**result.quote.__dict__),
        outbound_reply=OutboundReplyItem(**result.outbound_reply.__dict__),
    )


@router.post("/quotes/{quote_id}/reply", response_model=QuoteReplyResponse)
async def interpret_quote_reply(
    quote_id: str,
    payload: QuoteReplyPayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> QuoteReplyResponse:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    result = await container.quote_response_workflow.interpret_reply(
        InterpretQuoteReplyCommand(
            quote_id=quote_id,
            body_text=payload.body_text,
            mode=payload.mode,
            total_weight_kg=payload.total_weight_kg,
            requested_carrier_name=payload.requested_carrier_name,
            min_confidence=payload.min_confidence,
            revised_customer_price=payload.revised_customer_price,
        )
    )
    return QuoteReplyResponse(
        intent=result.intent.value,
        event=QuoteResponseEventItem(**result.event.__dict__),
        quote=QuoteListItem(**result.quote.__dict__) if result.quote else None,
        revised_quote=(
            QuoteListItem(**result.revised_quote.__dict__) if result.revised_quote else None
        ),
        shipment=(
            ShipmentListItem(**result.booking.shipment.__dict__) if result.booking else None
        ),
    )


@router.post("/quotes/{quote_id}/accept", response_model=AcceptQuoteResponse)
async def accept_quote(
    quote_id: str,
    payload: AcceptQuotePayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> AcceptQuoteResponse:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    result = await container.booking_workflow.book_quote(
        BookQuoteCommand(
            quote_id=quote_id,
            mode=payload.mode,
            total_weight_kg=payload.total_weight_kg,
            requested_carrier_name=payload.requested_carrier_name,
            min_confidence=payload.min_confidence,
        )
    )

    return AcceptQuoteResponse(
        shipment=ShipmentListItem(**result.shipment.__dict__),
        selected_carrier_id=result.selected_carrier_id,
        requires_manual_review=result.requires_manual_review,
        overall_confidence=result.overall_confidence,
    )
