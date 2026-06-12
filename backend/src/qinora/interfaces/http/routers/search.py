from fastapi import APIRouter, Query

from qinora.application import AuthContext, Role
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import SearchResultItem

router = APIRouter()


@router.get("/search", response_model=list[SearchResultItem])
async def global_search(
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=10, ge=1, le=25),
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> list[SearchResultItem]:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    return [
        SearchResultItem(**item.__dict__)
        for item in await container.operational_queries.global_search(q, limit)
    ]
