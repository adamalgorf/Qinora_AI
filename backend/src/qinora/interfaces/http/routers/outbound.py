"""Outbound delivery for both the customer-quote queue (outbound_reply_queue,
via OutboundReplyRepository) and the carrier-RFQ queue (carrier_rfq_outbound,
via CarrierRfqOutboundRepository - see application/pricing_engine.py and
migrations/0006_carrier_rfq.sql). Real sending happens outside this backend
entirely: the Gmail Apps Script bridge
(integrations/gmail-intake-bridge/Code.gs's sendQueuedReplies(), the
mirror-image of forwardNewMail()) polls next_queued below, calls
GmailApp.sendEmail(...) itself (this backend has no Gmail credentials), and
reports back via ack/fail. ProcessOutboundQueueUseCase/RecordingOutboundMailer
(application/outbound_mailer.py) still exist for tests and the
/emails/outbound/process admin endpoint, but nothing reachable in production
calls OutboundMailer.send() anymore - the real send path is entirely through
Code.gs hitting the endpoints below.

HMAC scheme (Code.gs must match this exactly - see the SETUP section at the
top of Code.gs): every endpoint here reuses the same
verify_hmac_signature()/EMAIL_WEBHOOK_SECRET trust boundary as
POST /webhooks/email - x-qinora-signature is HMAC-SHA256(secret, body) where
body is the exact bytes of the request body. GET /outbound/next-queued has
no body to sign; by convention the signature there is computed over an
empty byte string (Code.gs signs "" the same way, via
Utilities.computeHmacSha256Signature("", secret)) rather than over the URL -
simpler to keep byte-identical on both sides than canonicalizing a URL/query
string, and there's nothing in the request that needs authenticating besides
"is this Code.gs".
"""

from fastapi import APIRouter, Header, HTTPException, Request, status

from qinora.application import CollectCarrierRfqsCommand
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import CONTAINER
from qinora.interfaces.http.schemas import (
    CollectCarrierRfqsResponse,
    OutboundAckResponse,
    OutboundFailPayload,
    OutboundQueueItem,
)
from qinora.interfaces.http.security import verify_hmac_signature

router = APIRouter()

QUEUE_QUOTE = "quote"
QUEUE_CARRIER_RFQ = "carrier_rfq"


def _require_signature(container: AppContainer, body: bytes, signature: str | None) -> None:
    if not verify_hmac_signature(container.settings.email_webhook_secret, body, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")


@router.get("/outbound/next-queued", response_model=list[OutboundQueueItem])
async def next_queued(
    signature: str | None = Header(default=None, alias="x-qinora-signature"),
    limit: int = 20,
    container: AppContainer = CONTAINER,
) -> list[OutboundQueueItem]:
    _require_signature(container, b"", signature)

    quote_items = await container.outbound_reply_repository.next_queued(limit)
    carrier_items = await container.carrier_rfq_outbound_repository.next_queued(limit)

    return [
        OutboundQueueItem(
            queue=QUEUE_QUOTE,
            id=item.id,
            recipient=item.recipient,
            subject=item.subject,
            body_text=item.body_text,
        )
        for item in quote_items
    ] + [
        OutboundQueueItem(
            queue=QUEUE_CARRIER_RFQ,
            id=item.id,
            recipient=item.recipient,
            subject=item.subject,
            body_text=item.body_text,
        )
        for item in carrier_items
    ]


@router.post("/outbound/{queue}/{item_id}/ack", response_model=OutboundAckResponse)
async def ack_outbound(
    queue: str,
    item_id: str,
    request: Request,
    signature: str | None = Header(default=None, alias="x-qinora-signature"),
    container: AppContainer = CONTAINER,
) -> OutboundAckResponse:
    body = await request.body()
    _require_signature(container, body, signature)

    if queue == QUEUE_QUOTE:
        await container.outbound_reply_repository.mark_sent(item_id)
    elif queue == QUEUE_CARRIER_RFQ:
        await container.carrier_rfq_outbound_repository.mark_sent(item_id)
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown queue")

    return OutboundAckResponse()


@router.post("/outbound/{queue}/{item_id}/fail", response_model=OutboundAckResponse)
async def fail_outbound(
    queue: str,
    item_id: str,
    payload: OutboundFailPayload,
    request: Request,
    signature: str | None = Header(default=None, alias="x-qinora-signature"),
    container: AppContainer = CONTAINER,
) -> OutboundAckResponse:
    body = await request.body()
    _require_signature(container, body, signature)

    if queue == QUEUE_QUOTE:
        await container.outbound_reply_repository.mark_failed(item_id, payload.error_message)
    elif queue == QUEUE_CARRIER_RFQ:
        await container.carrier_rfq_outbound_repository.mark_failed(
            item_id, payload.error_message
        )
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown queue")

    return OutboundAckResponse()


@router.post("/outbound/collect-carrier-rfqs", response_model=CollectCarrierRfqsResponse)
async def collect_carrier_rfqs(
    request: Request,
    signature: str | None = Header(default=None, alias="x-qinora-signature"),
    window_hours: int = 24,
    container: AppContainer = CONTAINER,
) -> CollectCarrierRfqsResponse:
    """Piggybacks the periodic carrier-RFQ sweep
    (application/carrier_rfq_collector.py) onto the same trust boundary, and
    the same 5-minute Apps Script trigger that already drives
    sendQueuedReplies() (see integrations/gmail-intake-bridge/Code.gs) -
    the simplest option, since it needs no separate scheduler. There's no
    existing HTTP-triggered cron pattern in this codebase to follow instead
    (workers/stale_request_escalator.py and workers/outbound_mailer.py are
    both standalone scripts, not endpoints); workers/carrier_rfq_collector.py
    mirrors that standalone-script convention too, for a Render Cron Job or
    a manual run, in case Code.gs turns out not to be the right scheduler
    for this in production.
    """
    body = await request.body()
    _require_signature(container, body, signature)

    result = await container.carrier_rfq_collector.run(
        CollectCarrierRfqsCommand(window_hours=window_hours)
    )
    escalated = sum(1 for batch in result.finalized if batch.escalated)
    return CollectCarrierRfqsResponse(
        finalized=len(result.finalized) - escalated,
        escalated=escalated,
    )
