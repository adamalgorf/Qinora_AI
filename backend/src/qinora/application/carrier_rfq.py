"""Selects which carriers to send an automatic RFQ (request-for-quote) email
to when application/pricing_engine.py finds no matching rate_profile.

Reuses domain/carrier_intelligence.py's evaluate_carriers() - the exact same
scoring OperationalQueries.run_carrier_intelligence already uses to pick a
single carrier at booking time (see application/operational_queries.py) -
but keeps every *eligible* candidate that also has an email on file (there's
nowhere to send an RFQ without one), instead of just the top-ranked one,
since this pass contacts multiple carriers in parallel rather than picking
a single winner up front. evaluate_carriers() itself is untouched.
"""

from dataclasses import dataclass

from qinora.application.operational_queries import OperationalQueries
from qinora.application.read_models import CarrierRecord
from qinora.domain import (
    CarrierCandidate,
    CarrierEvaluationInput,
    TransportMode,
    evaluate_carriers,
    parse_transport_modes,
)

DEFAULT_MAX_RFQ_TARGETS = 3


@dataclass(frozen=True)
class SelectRfqTargetsCommand:
    mode: str
    total_weight_kg: float
    max_targets: int = DEFAULT_MAX_RFQ_TARGETS


class CarrierRfqTargeting:
    def __init__(self, operational_queries: OperationalQueries) -> None:
        self._operational_queries = operational_queries

    async def select_targets(self, command: SelectRfqTargetsCommand) -> tuple[CarrierRecord, ...]:
        carriers = await self._operational_queries.list_carriers()
        with_email = {carrier.id: carrier for carrier in carriers if carrier.email}
        if not with_email:
            return ()

        candidates = tuple(
            CarrierCandidate(
                id=carrier.id,
                display_name=carrier.display_name,
                aliases=carrier.aliases,
                modes=parse_transport_modes(carrier.modes),
                lane_score=carrier.lane_score,
                max_weight_kg=carrier.max_weight_kg,
                performance_score=carrier.performance_score,
                preferred=carrier.preferred,
                sample_size=carrier.sample_size,
            )
            for carrier in with_email.values()
        )

        evaluation = evaluate_carriers(
            CarrierEvaluationInput(
                mode=TransportMode(command.mode),
                total_weight_kg=command.total_weight_kg,
                candidates=candidates,
            )
        )
        eligible_ids = [
            item.carrier_id for item in evaluation.evaluations if item.status == "eligible"
        ]
        return tuple(with_email[carrier_id] for carrier_id in eligible_ids[: command.max_targets])
