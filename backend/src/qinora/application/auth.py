from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    SHIPPER = "shipper"
    CARRIER = "carrier"
    TOWER = "4pl_tower"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    tenant_id: str
    roles: frozenset[Role]

    def has_any_role(self, required_roles: set[Role]) -> bool:
        return bool(self.roles.intersection(required_roles))


class AuthorizationError(PermissionError):
    pass


def require_any_role(context: AuthContext, *roles: Role) -> None:
    required = set(roles)
    if not context.has_any_role(required):
        allowed = ", ".join(role.value for role in roles)
        raise AuthorizationError(f"Requires one of: {allowed}")
