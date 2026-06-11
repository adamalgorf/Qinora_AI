from fastapi import Header, HTTPException, status

from qinora.application.auth import AuthContext, AuthorizationError, Role, require_any_role


async def get_auth_context(
    user_id: str = Header(default="dev-user", alias="x-user-id"),
    tenant_id: str = Header(default="dev-tenant", alias="x-tenant-id"),
    roles_header: str = Header(default=Role.ADMIN.value, alias="x-role"),
) -> AuthContext:
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
