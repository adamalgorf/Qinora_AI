from fastapi import APIRouter

from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import CONTAINER
from qinora.interfaces.http.schemas import DashboardSummaryResponse, OperationalTaskItem

router = APIRouter()


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(container: AppContainer = CONTAINER) -> DashboardSummaryResponse:
    summary = await container.operational_queries.dashboard_summary()
    return DashboardSummaryResponse.model_validate(summary.__dict__)


@router.get("/tasks", response_model=list[OperationalTaskItem])
async def list_operational_tasks(container: AppContainer = CONTAINER) -> list[OperationalTaskItem]:
    return [
        OperationalTaskItem(**item.__dict__)
        for item in await container.operational_queries.list_operational_tasks()
    ]
