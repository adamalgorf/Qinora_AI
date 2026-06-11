from fastapi import APIRouter

from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import CONTAINER
from qinora.interfaces.http.schemas import DashboardSummaryResponse

router = APIRouter()


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(container: AppContainer = CONTAINER) -> DashboardSummaryResponse:
    summary = await container.operational_queries.dashboard_summary()
    return DashboardSummaryResponse.model_validate(summary.__dict__)
