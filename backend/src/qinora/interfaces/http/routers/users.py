from fastapi import APIRouter, HTTPException, status

from qinora.application import AuthContext, Role
from qinora.application.read_models import UserRecord
from qinora.infrastructure.passwords import hash_password
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER, ContainerDep
from qinora.interfaces.http.schemas import (
    CreateUserRequest,
    ResetPasswordRequest,
    UpdateUserRequest,
    UserListItem,
)

router = APIRouter()


@router.get("/users", response_model=list[UserListItem])
async def list_users(
    container: ContainerDep = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> list[UserListItem]:
    require_roles(context, Role.ADMIN, Role.SUPERADMIN)
    users = await container.user_repository.list_users()
    return [_to_user_list_item(user) for user in users]


@router.post("/users", response_model=UserListItem, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    container: ContainerDep = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> UserListItem:
    require_roles(context, Role.ADMIN, Role.SUPERADMIN)
    try:
        roles = tuple(Role(role).value for role in payload.roles)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid role",
        ) from error

    existing = await container.user_repository.find_by_email(payload.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = await container.user_repository.create_user(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.temporary_password),
        roles=roles,
    )
    return _to_user_list_item(user)


@router.patch("/users/{target_user_id}", response_model=UserListItem)
async def update_user(
    target_user_id: str,
    payload: UpdateUserRequest,
    container: ContainerDep = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> UserListItem:
    require_roles(context, Role.ADMIN, Role.SUPERADMIN)
    user = await container.user_repository.find_by_id(target_user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.is_active is False and target_user_id == context.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )

    if payload.roles is not None:
        try:
            roles = tuple(Role(role).value for role in payload.roles)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid role",
            ) from error
        await container.user_repository.set_roles(target_user_id, roles)

    if payload.is_active is not None:
        await container.user_repository.set_active(target_user_id, payload.is_active)

    updated = await container.user_repository.find_by_id(target_user_id)
    assert updated is not None
    return _to_user_list_item(updated)


@router.post("/users/{target_user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    target_user_id: str,
    payload: ResetPasswordRequest,
    container: ContainerDep = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> None:
    require_roles(context, Role.ADMIN, Role.SUPERADMIN)
    user = await container.user_repository.find_by_id(target_user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await container.user_repository.set_password(
        target_user_id, hash_password(payload.temporary_password)
    )


def _to_user_list_item(user: UserRecord) -> UserListItem:
    return UserListItem(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=list(user.roles),
        is_active=user.is_active,
    )
