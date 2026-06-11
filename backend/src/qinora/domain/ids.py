from enum import StrEnum


class EntityPrefix(StrEnum):
    REQUEST = "REQ"
    QUOTE = "QUO"
    SHIPMENT = "SHP"
    INVOICE = "INV"
    CARRIER = "CAR"
    CONTACT = "CNT"


def format_public_id(prefix: EntityPrefix, sequence: int) -> str:
    if sequence < 0:
        raise ValueError("sequence must be non-negative")

    return f"{prefix.value}-{sequence:04d}"
