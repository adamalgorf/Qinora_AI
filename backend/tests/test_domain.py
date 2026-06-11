from datetime import UTC, datetime

import pytest

from qinora.domain import (
    CargoLineInput,
    CarrierCandidate,
    CarrierEvaluationInput,
    CurrencyCode,
    EntityPrefix,
    Money,
    Quote,
    QuoteStatus,
    ShipmentStatus,
    TransportMode,
    TransportRequestInput,
    assert_shipment_transition,
    can_send_quote,
    evaluate_carriers,
    format_public_id,
    next_quote_revision,
    validate_transport_request,
)
from qinora.domain.shipment_status import InvalidShipmentTransition


def test_formats_public_entity_ids() -> None:
    assert format_public_id(EntityPrefix.REQUEST, 42) == "REQ-0042"


def test_enforces_shipment_fsm() -> None:
    assert_shipment_transition(ShipmentStatus.BOOKED, ShipmentStatus.IN_TRANSIT)

    with pytest.raises(InvalidShipmentTransition):
        assert_shipment_transition(ShipmentStatus.INVOICE_APPROVED, ShipmentStatus.CANCELLED)


def test_validates_intake_and_detects_adr() -> None:
    result = validate_transport_request(
        TransportRequestInput(
            mode=TransportMode.LTL,
            cargo=(CargoLineInput(description="Paint UN1263", weight_kg=120),),
        )
    )

    assert not result.complete
    assert result.adr_findings[0].un_number == "UN1263"
    assert "cargo.0.length_cm" in {issue.field for issue in result.issues}


def test_complete_intake_passes_validation() -> None:
    result = validate_transport_request(
        TransportRequestInput(
            mode=TransportMode.FTL,
            cargo=(
                CargoLineInput(
                    description="Pallets",
                    weight_kg=120,
                    length_cm=120,
                    width_cm=80,
                    height_cm=160,
                ),
            ),
            loading_time=datetime(2026, 6, 11, 10, tzinfo=UTC),
        )
    )

    assert result.complete


def test_blocks_zero_price_quote() -> None:
    quote = Quote(
        id="quote-1",
        status=QuoteStatus.DRAFT,
        version=1,
        customer_price=Money(amount=0, currency=CurrencyCode.SEK),
    )

    allowed, reason = can_send_quote(quote)

    assert not allowed
    assert reason == "Quote customer price must be greater than zero"


def test_versions_revised_quotes_from_original_parent() -> None:
    quote = Quote(
        id="quote-2",
        status=QuoteStatus.SENT,
        version=2,
        parent_quote_id="quote-1",
        customer_price=Money(amount=500, currency=CurrencyCode.SEK),
    )

    assert next_quote_revision(quote) == (3, "quote-1")


def test_carrier_intelligence_selects_best_carrier() -> None:
    result = evaluate_carriers(
        CarrierEvaluationInput(
            mode=TransportMode.FTL,
            total_weight_kg=500,
            requested_carrier_name="Nordic",
            candidates=(
                CarrierCandidate(
                    id="carrier-a",
                    display_name="Nordic Freight",
                    aliases=("Nordic",),
                    modes=(TransportMode.FTL,),
                    max_weight_kg=1000,
                    lane_score=90,
                    performance_score=92,
                    preferred=True,
                    sample_size=80,
                ),
                CarrierCandidate(
                    id="carrier-b",
                    display_name="Baltic Logistics",
                    aliases=(),
                    modes=(TransportMode.FTL,),
                    max_weight_kg=1000,
                    lane_score=70,
                    performance_score=72,
                    sample_size=20,
                ),
            ),
        )
    )

    assert result.selected_carrier_id == "carrier-a"
    assert not result.requires_manual_review
    assert result.evaluations[0].rank == 1
