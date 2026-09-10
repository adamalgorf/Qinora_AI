from fastapi import APIRouter

from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import CONTAINER
from qinora.interfaces.http.schemas import AutomationListItem

router = APIRouter()


@router.get("/automations", response_model=list[AutomationListItem])
async def list_automations(container: AppContainer = CONTAINER) -> list[AutomationListItem]:
    configs = await container.agent_config_service.list_configs()
    automations = await container.operational_queries.list_automations(configs)
    return [AutomationListItem(**item.__dict__) for item in automations]
