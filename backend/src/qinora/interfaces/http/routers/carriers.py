from fastapi import APIRouter

from qinora.application import AuthContext, CarrierIntelligenceCommand, Role
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    CarrierIntelligenceRequest,
    CarrierIntelligenceResponse,
    CarrierListItem,
)

router = APIRouter()


@router.get("/carriers", response_model=list[CarrierListItem])
async def list_carriers(container: AppContainer = CONTAINER) -> list[CarrierListItem]:
    return [
        CarrierListItem(
            id=item.id,
            display_name=item.display_name,
            modes=list(item.modes),
            lane_score=item.lane_score,
            performance_score=item.performance_score,
            preferred=item.preferred,
        )
        for item in await container.operational_queries.list_carriers()
    ]


@router.post("/carriers/intelligence", response_model=CarrierIntelligenceResponse)
async def run_carrier_intelligence(
    payload: CarrierIntelligenceRequest,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> CarrierIntelligenceResponse:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    result = await container.operational_queries.run_carrier_intelligence(
        CarrierIntelligenceCommand(
            mode=payload.mode,
            total_weight_kg=payload.total_weight_kg,
            requested_carrier_name=payload.requested_carrier_name,
            min_confidence=payload.min_confidence,
        )
    )

    return CarrierIntelligenceResponse(
        selected_carrier_id=result.selected_carrier_id,
        requires_manual_review=result.requires_manual_review,
        overall_confidence=result.overall_confidence,
        evaluations=[
            {
                "carrier_id": item.carrier_id,
                "rank": item.rank,
                "status": item.status,
                "score_total": item.score_total,
                "reasons": list(item.reasons),
            }
            for item in result.evaluations
        ],
    )
