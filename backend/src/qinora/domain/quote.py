from dataclasses import dataclass
from enum import StrEnum


class CurrencyCode(StrEnum):
    SEK = "SEK"
    EUR = "EUR"
    USD = "USD"
    NOK = "NOK"
    DKK = "DKK"


class QuoteStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVISION_REQUESTED = "revision_requested"
    REVISED = "revised"
    CONVERTED = "converted"


@dataclass(frozen=True)
class Money:
    amount: float
    currency: CurrencyCode


@dataclass(frozen=True)
class Quote:
    id: str
    status: QuoteStatus
    version: int
    customer_price: Money
    parent_quote_id: str | None = None


def can_send_quote(quote: Quote) -> tuple[bool, str | None]:
    if quote.status not in {QuoteStatus.DRAFT, QuoteStatus.REVISED}:
        return False, f"Quote status {quote.status.value} cannot be sent"

    if quote.customer_price.amount <= 0:
        return False, "Quote customer price must be greater than zero"

    return True, None


def next_quote_revision(previous: Quote) -> tuple[int, str]:
    return previous.version + 1, previous.parent_quote_id or previous.id
