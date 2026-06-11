from dataclasses import dataclass

from qinora.application.ports import OperationalReadRepository
from qinora.application.read_models import (
    AgentLogRecord,
    CarrierRecord,
    InboxRecord,
    QuoteRecord,
    RequestRecord,
    ShipmentRecord,
)
from qinora.domain import CarrierCandidate, CarrierEvaluationInput, TransportMode, evaluate_carriers


@dataclass(frozen=True)
class DashboardSummary:
    kpis: list[dict[str, str]]
    pipeline: list[dict[str, int | str]]
    agent_activity: list[dict[str, float | str]]


@dataclass(frozen=True)
class CarrierIntelligenceCommand:
    mode: str
    total_weight_kg: float
    requested_carrier_name: str | None
    min_confidence: float


class OperationalQueries:
    def __init__(self, repository: OperationalReadRepository) -> None:
        self._repository = repository

    async def dashboard_summary(self) -> DashboardSummary:
        requests = await self._repository.list_requests()
        shipments = await self._repository.list_shipments()
        agent_logs = await self._repository.list_agent_logs()
        exceptions = len([item for item in shipments if item.status == "needs_review"])
        open_requests = len([item for item in requests if item.status != "converted"])

        return DashboardSummary(
            kpis=[
                {"label": "Open requests", "value": str(open_requests), "trend": "+12%"},
                {"label": "On-time", "value": "96%", "trend": "+3%"},
                {"label": "Exceptions", "value": str(exceptions), "trend": "-18%"},
                {"label": "Agent health", "value": "98%", "trend": "+1%"},
            ],
            pipeline=[
                {"status": "New", "count": 8},
                {"status": "Parsing", "count": 3},
                {"status": "Quoted", "count": 12},
                {"status": "Booked", "count": 9},
                {"status": "In transit", "count": 17},
                {"status": "Needs review", "count": exceptions},
            ],
            agent_activity=[
                {
                    "agent": log.agent_name,
                    "event": log.step,
                    "confidence": log.confidence,
                }
                for log in agent_logs
            ],
        )

    async def list_requests(self) -> list[RequestRecord]:
        return await self._repository.list_requests()

    async def list_quotes(self) -> list[QuoteRecord]:
        return await self._repository.list_quotes()

    async def list_shipments(self) -> list[ShipmentRecord]:
        return await self._repository.list_shipments()

    async def list_carriers(self) -> list[CarrierRecord]:
        return await self._repository.list_carriers()

    async def list_inbox(self) -> list[InboxRecord]:
        return await self._repository.list_inbox()

    async def list_agent_logs(self) -> list[AgentLogRecord]:
        return await self._repository.list_agent_logs()

    async def run_carrier_intelligence(self, command: CarrierIntelligenceCommand):
        carriers = await self._repository.list_carriers()
        candidates = tuple(_to_candidate(carrier) for carrier in carriers)

        return evaluate_carriers(
            CarrierEvaluationInput(
                mode=TransportMode(command.mode),
                total_weight_kg=command.total_weight_kg,
                requested_carrier_name=command.requested_carrier_name,
                min_confidence=command.min_confidence,
                candidates=candidates,
            )
        )


def _to_candidate(carrier: CarrierRecord) -> CarrierCandidate:
    return CarrierCandidate(
        id=carrier.id,
        display_name=carrier.display_name,
        aliases=carrier.aliases,
        modes=tuple(TransportMode(mode) for mode in carrier.modes),
        lane_score=carrier.lane_score,
        max_weight_kg=carrier.max_weight_kg,
        performance_score=carrier.performance_score,
        preferred=carrier.preferred,
        sample_size=carrier.sample_size,
    )
