from fastapi import Header, HTTPException, Request, status

from qinora.application.auth import AuthContext, AuthorizationError, Role, require_any_role
from qinora.interfaces.http.security import AuthTokenError, parse_auth_token


async def get_auth_context(
    request: Request,
    authorization: str | None = Header(default=None, alias="authorization"),
    user_id: str = Header(default="dev-user", alias="x-user-id"),
    tenant_id: str = Header(default="dev-tenant", alias="x-tenant-id"),
    roles_header: str = Header(default=Role.ADMIN.value, alias="x-role"),
) -> AuthContext:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header",
            )
        try:
            return parse_auth_token(token, request.app.state.container.settings.auth_token_secret)
        except AuthTokenError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(error),
            ) from error

    try:
        roles = frozenset(Role(role.strip()) for role in roles_header.split(",") if role.strip())
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid role header",
        ) from error

    return AuthContext(user_id=user_id, tenant_id=tenant_id, roles=roles)


def require_roles(context: AuthContext, *roles: Role) -> None:
    try:
        require_any_role(context, *roles)
    except AuthorizationError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(error),
        ) from error
