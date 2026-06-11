from fastapi import APIRouter, HTTPException, status

from qinora.application import AuthContext, Role
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER, ContainerDep
from qinora.interfaces.http.schemas import AuthMeResponse, DevTokenRequest, TokenResponse
from qinora.interfaces.http.security import create_auth_token

router = APIRouter()
DEV_TOKEN_TTL_SECONDS = 60 * 60 * 8


@router.get("/auth/me", response_model=AuthMeResponse)
async def auth_me(context: AuthContext = AUTH_CONTEXT) -> AuthMeResponse:
    return _to_auth_me_response(context)


@router.post("/auth/dev-token", response_model=TokenResponse)
async def create_dev_token(
    payload: DevTokenRequest,
    container: ContainerDep = CONTAINER,
) -> TokenResponse:
    try:
        context = AuthContext(
            user_id=payload.user_id,
            tenant_id=payload.tenant_id,
            roles=frozenset(Role(role) for role in payload.roles),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid role",
        ) from error
    return TokenResponse(
        access_token=create_auth_token(
            context,
            container.settings.auth_token_secret,
            expires_in_seconds=DEV_TOKEN_TTL_SECONDS,
        ),
        expires_in=DEV_TOKEN_TTL_SECONDS,
        user=_to_auth_me_response(context),
    )


def _to_auth_me_response(context: AuthContext) -> AuthMeResponse:
    return AuthMeResponse(
        user_id=context.user_id,
        tenant_id=context.tenant_id,
        roles=[role.value for role in sorted(context.roles, key=lambda role: role.value)],
    )
