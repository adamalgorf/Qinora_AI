from fastapi import APIRouter

from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import CONTAINER
from qinora.interfaces.http.schemas import (
    AnalyticsKpiItem,
    AnalyticsSummaryResponse,
    ExceptionCategoryItem,
    WorkloadByWeekdayItem,
)

router = APIRouter()


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
async def analytics_summary(container: AppContainer = CONTAINER) -> AnalyticsSummaryResponse:
    summary = await container.operational_queries.analytics_summary()
    return AnalyticsSummaryResponse(
        kpis=[AnalyticsKpiItem(**item) for item in summary.kpis],
        workload_by_weekday=[WorkloadByWeekdayItem(**item) for item in summary.workload_by_weekday],
        top_exception_categories=[
            ExceptionCategoryItem(**item) for item in summary.top_exception_categories
        ],
    )
