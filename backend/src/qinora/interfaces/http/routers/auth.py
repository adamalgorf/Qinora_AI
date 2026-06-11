from fastapi import APIRouter

from qinora.application import AuthContext
from qinora.interfaces.http.dependencies import AUTH_CONTEXT
from qinora.interfaces.http.schemas import AuthMeResponse

router = APIRouter()


@router.get("/auth/me", response_model=AuthMeResponse)
async def auth_me(context: AuthContext = AUTH_CONTEXT) -> AuthMeResponse:
    return AuthMeResponse(
        user_id=context.user_id,
        tenant_id=context.tenant_id,
        roles=[role.value for role in sorted(context.roles, key=lambda role: role.value)],
    )
