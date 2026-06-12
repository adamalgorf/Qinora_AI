from fastapi import APIRouter, HTTPException, status

from qinora.application import AuthContext, Role, UpdateAgentConfigCommand
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import (
    AgentConfigItem,
    AgentLogListItem,
    UpdateAgentConfigPayload,
)

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


@router.get("/agents/configs", response_model=list[AgentConfigItem])
async def agent_configs(
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> list[AgentConfigItem]:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    return [
        AgentConfigItem(**item.__dict__)
        for item in await container.agent_config_service.list_configs()
    ]


@router.post("/agents/{agent_key}/config", response_model=AgentConfigItem)
async def update_agent_config(
    agent_key: str,
    payload: UpdateAgentConfigPayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> AgentConfigItem:
    require_roles(context, Role.ADMIN, Role.SUPERADMIN)
    try:
        config = await container.agent_config_service.update_config(
            UpdateAgentConfigCommand(
                agent_key=agent_key,
                is_enabled=payload.is_enabled,
                auto_mode=payload.auto_mode,
                min_confidence=payload.min_confidence,
            )
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return AgentConfigItem(**config.__dict__)
