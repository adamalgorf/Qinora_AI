from fastapi import APIRouter, HTTPException, status

from qinora.application import AuthContext, Role
from qinora.infrastructure.passwords import hash_password, verify_password
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER, ContainerDep
from qinora.interfaces.http.schemas import (
    AuthConfigResponse,
    AuthMeResponse,
    ChangePasswordRequest,
    DevTokenRequest,
    LoginRequest,
    TokenResponse,
)
from qinora.interfaces.http.security import create_auth_token

router = APIRouter()
DEV_TOKEN_TTL_SECONDS = 60 * 60 * 8
LOGIN_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
INVALID_CREDENTIALS_DETAIL = "Invalid email or password"


@router.get("/auth/config", response_model=AuthConfigResponse)
async def auth_config(container: ContainerDep = CONTAINER) -> AuthConfigResponse:
    return AuthConfigResponse(login_required=container.settings.require_auth)


@router.get("/auth/me", response_model=AuthMeResponse)
async def auth_me(context: AuthContext = AUTH_CONTEXT) -> AuthMeResponse:
    return _to_auth_me_response(context)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    container: ContainerDep = CONTAINER,
) -> TokenResponse:
    user = await container.user_repository.find_by_email(payload.email)
    if (
        user is None
        or not user.is_active
        or not user.password_hash
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS_DETAIL,
        )

    context = AuthContext(
        user_id=user.id,
        tenant_id=container.settings.postgres_tenant_id,
        roles=frozenset(Role(role) for role in user.roles),
    )
    return TokenResponse(
        access_token=create_auth_token(
            context,
            container.settings.auth_token_secret,
            expires_in_seconds=LOGIN_TOKEN_TTL_SECONDS,
        ),
        expires_in=LOGIN_TOKEN_TTL_SECONDS,
        user=_to_auth_me_response(context),
    )


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    container: ContainerDep = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> None:
    user = await container.user_repository.find_by_id(context.user_id)
    if (
        user is None
        or not user.password_hash
        or not verify_password(payload.current_password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid current password",
        )
    await container.user_repository.set_password(user.id, hash_password(payload.new_password))


@router.post("/auth/dev-token", response_model=TokenResponse)
async def create_dev_token(
    payload: DevTokenRequest,
    container: ContainerDep = CONTAINER,
) -> TokenResponse:
    if container.settings.require_auth:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
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
