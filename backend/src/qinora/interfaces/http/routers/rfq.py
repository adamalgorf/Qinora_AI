from fastapi import APIRouter, status

from qinora.application import AuthContext, Role
from qinora.application.llm_dtos import RFQAnalysisRequest, RFQAnalysisResponse
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER

router = APIRouter()


@router.post(
    "/rfq/analyze",
    response_model=RFQAnalysisResponse,
    status_code=status.HTTP_200_OK,
)
async def analyze_rfq(
    payload: RFQAnalysisRequest,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> RFQAnalysisResponse:
    """Runs the extract -> compare -> recommend graph over an RFQ document
    against a reference spec. The full decision_path is returned so the
    reasoning behind extracted_data/confidence_score stays visible to the
    caller rather than being a black box.
    """
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    return await container.analyze_rfq_use_case.execute(payload)
