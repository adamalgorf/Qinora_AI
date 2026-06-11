from fastapi import APIRouter

from qinora.application import AuthContext, Role
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import AgentLogListItem

router = APIRouter()


@router.get("/agents/logs", response_model=list[AgentLogListItem])
async def agent_logs(
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> list[AgentLogListItem]:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    return [
        AgentLogListItem(**item.__dict__)
        for item in await container.operational_queries.list_agent_logs()
    ]
