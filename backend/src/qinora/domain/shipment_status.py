from enum import StrEnum


class ShipmentStatus(StrEnum):
    DRAFT = "draft"
    QUOTE_SENT = "quote_sent"
    BOOKED = "booked"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    NEEDS_REVIEW = "needs_review"
    MANUAL_REVIEW = "manual_review"
    INVOICE_DISPUTED = "invoice_disputed"
    INVOICE_APPROVED = "invoice_approved"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[ShipmentStatus, set[ShipmentStatus]] = {
    ShipmentStatus.DRAFT: {
        ShipmentStatus.QUOTE_SENT,
        ShipmentStatus.BOOKED,
        ShipmentStatus.NEEDS_REVIEW,
        ShipmentStatus.CANCELLED,
    },
    ShipmentStatus.QUOTE_SENT: {
        ShipmentStatus.BOOKED,
        ShipmentStatus.NEEDS_REVIEW,
        ShipmentStatus.CANCELLED,
    },
    ShipmentStatus.BOOKED: {
        ShipmentStatus.IN_TRANSIT,
        ShipmentStatus.NEEDS_REVIEW,
        ShipmentStatus.CANCELLED,
    },
    ShipmentStatus.IN_TRANSIT: {
        ShipmentStatus.DELIVERED,
        ShipmentStatus.NEEDS_REVIEW,
        ShipmentStatus.CANCELLED,
    },
    ShipmentStatus.DELIVERED: {
        ShipmentStatus.INVOICE_APPROVED,
        ShipmentStatus.INVOICE_DISPUTED,
        ShipmentStatus.NEEDS_REVIEW,
    },
    ShipmentStatus.NEEDS_REVIEW: {
        ShipmentStatus.DRAFT,
        ShipmentStatus.BOOKED,
        ShipmentStatus.IN_TRANSIT,
        ShipmentStatus.MANUAL_REVIEW,
        ShipmentStatus.CANCELLED,
    },
    ShipmentStatus.MANUAL_REVIEW: {
        ShipmentStatus.DRAFT,
        ShipmentStatus.BOOKED,
        ShipmentStatus.NEEDS_REVIEW,
        ShipmentStatus.CANCELLED,
    },
    ShipmentStatus.INVOICE_DISPUTED: {
        ShipmentStatus.INVOICE_APPROVED,
        ShipmentStatus.NEEDS_REVIEW,
    },
    ShipmentStatus.INVOICE_APPROVED: set(),
    ShipmentStatus.CANCELLED: set(),
}


class InvalidShipmentTransition(ValueError):
    pass


def assert_shipment_transition(from_status: ShipmentStatus, to_status: ShipmentStatus) -> None:
    if from_status == to_status:
        return

    if to_status not in ALLOWED_TRANSITIONS[from_status]:
        raise InvalidShipmentTransition(
            f"Shipment cannot transition from {from_status.value} to {to_status.value}"
        )
